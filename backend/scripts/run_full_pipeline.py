import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so `backend.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import HTTPException

from backend.agents.conversation.graph import build_graph
from backend.agents.conversation.models import ConversationState, UIPlan
from backend.agents.conversation.validators import evaluate_quality_gate
from backend.api.routes import CompileRequest, EmitRequest, compile_ir, emit_code
from backend.core.session import compiled_ir_log_path, get_session, save_session
from backend.core.setting import get_settings


def _as_state(value: ConversationState | dict[str, Any]) -> ConversationState:
    if isinstance(value, ConversationState):
        return value
    return ConversationState.model_validate(value)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned or "session"


def _read_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def _last_assistant_message(state: ConversationState) -> str:
    for message in reversed(state.messages):
        if message.role == "assistant":
            return message.content
    return ""


def _next_input(
    *,
    state: ConversationState,
    scripted: list[str] | None,
    index: int,
    auto_confirm: bool,
) -> tuple[str | None, int]:
    if scripted is None:
        try:
            text = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            return None, index
        return text, index

    if index < len(scripted):
        return scripted[index], index + 1

    if auto_confirm and state.mode == "confirm":
        return "yes", index

    return None, index


async def run_pipeline(args: argparse.Namespace) -> int:
    settings = get_settings()
    timestamp = _utc_stamp()
    session_id = args.session_id or f"pipeline-{timestamp}"

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / f"full_pipeline_{timestamp}_{_sanitize(session_id)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    scripted_inputs: list[str] | None = None
    if args.input_file:
        scripted_inputs = _read_lines(Path(args.input_file))
    if args.message:
        scripted_inputs = (scripted_inputs or []) + args.message

    state = get_session(session_id)
    graph = build_graph()

    transcript: list[dict[str, Any]] = []
    scripted_index = 0
    turn = 0

    print(f"session_id={session_id}")
    print(f"run_dir={run_dir}")
    if scripted_inputs is None:
        print("mode=interactive")
    else:
        print(f"mode=scripted inputs={len(scripted_inputs)} auto_confirm={args.auto_confirm}")

    while turn < args.max_turns:
        user_input, scripted_index = _next_input(
            state=state,
            scripted=scripted_inputs,
            index=scripted_index,
            auto_confirm=args.auto_confirm,
        )

        if user_input is None:
            print("input_exhausted=true")
            break

        user_input = user_input.strip()
        if not user_input:
            if scripted_inputs is not None:
                continue
            print("empty_input=true")
            continue

        if user_input.lower() == "quit":
            print("quit_received=true")
            break

        state.add_message("user", user_input)
        state = _as_state(await graph.ainvoke(state))
        save_session(session_id, state)

        assistant = _last_assistant_message(state)
        gate = evaluate_quality_gate(
            state.fields,
            gate_mode=settings.quality_gate_mode,
        )

        turn += 1
        print(
            f"turn={turn} mode={state.mode} confirmed={state.confirmed} "
            f"missing={state.missing} blocking={len(gate.blocking_findings)}"
        )
        if assistant:
            preview = assistant.replace("\n", " ")
            print(f"assistant={preview[:180]}")

        transcript.append(
            {
                "turn": turn,
                "user": user_input,
                "assistant": assistant,
                "mode": state.mode,
                "confirmed": state.confirmed,
                "missing": state.missing,
                "blocking_findings": [item.message for item in gate.blocking_findings],
                "state": state.model_dump(exclude_none=True),
            }
        )

        if state.mode == "done":
            break

    _write_json(run_dir / "transcript.json", transcript)

    if state.mode != "done":
        print("status=incomplete")
        print("hint=conversation did not reach done mode before input/turn limit.")
        return 2

    ui_plan = UIPlan.from_spec(state.fields)
    ui_plan_data = ui_plan.model_dump(exclude_none=True)
    _write_json(run_dir / "ui_plan.json", ui_plan_data)
    _write_json(PROJECT_ROOT / "ui_plan.json", ui_plan_data)

    try:
        compiled = await compile_ir(CompileRequest(session_id=session_id))
    except HTTPException as exc:
        payload = {
            "status": "compile_error",
            "http_status": exc.status_code,
            "detail": exc.detail,
            "session_id": session_id,
        }
        _write_json(run_dir / "compile_error.json", payload)
        print(f"status=compile_error http_status={exc.status_code}")
        print(f"detail={exc.detail}")
        return 3

    compile_data = compiled.model_dump(exclude_none=True)
    _write_json(run_dir / "compile_response.json", compile_data)

    try:
        emitted = await emit_code(EmitRequest(session_id=session_id))
    except HTTPException as exc:
        payload = {
            "status": "emit_error",
            "http_status": exc.status_code,
            "detail": exc.detail,
            "session_id": session_id,
        }
        _write_json(run_dir / "emit_error.json", payload)
        print(f"status=emit_error http_status={exc.status_code}")
        print(f"detail={exc.detail}")
        return 4

    emit_data = emitted.model_dump(exclude_none=True)
    _write_json(run_dir / "emit_response.json", emit_data)

    page_code = emitted.files.get("Page.tsx", "")
    page_path = run_dir / "Page.tsx"
    page_path.write_text(page_code, encoding="utf-8")

    # Compatibility artifact alongside other logs.
    compat_page = output_root / f"{session_id}_Page.tsx"
    compat_page.write_text(page_code, encoding="utf-8")

    compiled_path = compiled_ir_log_path(session_id)
    summary = {
        "status": "ok",
        "session_id": session_id,
        "run_dir": str(run_dir),
        "ui_plan_path": str(run_dir / "ui_plan.json"),
        "compiled_ir_path": str(compiled_path),
        "compiled_ir_exists": compiled_path.exists(),
        "page_path": str(page_path),
        "compat_page_path": str(compat_page),
        "emit_page_len": len(page_code),
        "compile_metadata": compile_data.get("metadata", {}),
        "audit_blocked": emit_data.get("audit_report", {}).get("blocked"),
        "audit_engine": emit_data.get("audit_report", {}).get("engine"),
    }
    _write_json(run_dir / "summary.json", summary)

    print("status=ok")
    print(f"ui_plan={run_dir / 'ui_plan.json'}")
    print(f"compiled_ir={compiled_path}")
    print(f"page_tsx={page_path}")
    print(f"page_tsx_compat={compat_page}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run full pipeline: conversation -> compile IR -> emit React code.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session id to use. Default: auto-generated pipeline-<timestamp>.",
    )
    parser.add_argument(
        "--output-dir",
        default=".logs",
        help="Output directory for run artifacts (default: .logs).",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Scripted user inputs file (one message per line).",
    )
    parser.add_argument(
        "--message",
        action="append",
        default=[],
        help="Add a scripted user message. Can be repeated.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Maximum conversation turns before stopping (default: 30).",
    )
    parser.add_argument(
        "--auto-confirm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When scripted input is exhausted in confirm mode, auto-send 'yes' (default: true).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_pipeline(args)))


if __name__ == "__main__":
    main()

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


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    WHITE = "\033[97m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BG_DARK = "\033[40m"
    BG_NAVY = "\033[44m"
    BG_GREEN = "\033[42m\033[30m"


WIDTH = 88


def divider(char: str = "─", color: str = C.DIM) -> None:
    print(f"{color}{char * WIDTH}{C.RESET}")


def header(text: str, color: str = C.BG_NAVY) -> None:
    pad = WIDTH - len(text) - 4
    print(f"\n{color}{C.BOLD}  {text}{' ' * max(pad, 0)}  {C.RESET}")


def print_user_prompt() -> None:
    print(f"{C.GREEN}{C.BOLD}  You ›{C.RESET} ", end="", flush=True)


def print_assistant(content: str, agent: str) -> None:
    print(f"\n{C.CYAN}{C.BOLD}  ● {agent}{C.RESET}")
    for line in content.splitlines():
        print(f"{C.CYAN}  │ {C.RESET}{line}")
    print()


def _fmt_value(value: object) -> str:
    if value is None:
        return "missing"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        if not value:
            return "missing"
        return ", ".join(
            json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value)


def print_state_snapshot(state: ConversationState, *, blocking_count: int) -> None:
    header("  STATE SNAPSHOT", color=C.BG_DARK)
    divider()

    mode_color = {
        "free_chat": C.YELLOW,
        "fill_gaps": C.MAGENTA,
        "confirm": C.CYAN,
        "done": C.GREEN,
    }.get(state.mode, C.WHITE)

    print(f"  {C.DIM}mode         {C.RESET}{mode_color}{C.BOLD}{state.mode}{C.RESET}")
    print(f"  {C.DIM}active_agent {C.RESET}{C.WHITE}{state.active_agent or '—'}{C.RESET}")
    print(f"  {C.DIM}turns        {C.RESET}{C.WHITE}{state.free_chat_turns()}{C.RESET}")
    print(f"  {C.DIM}confirmed    {C.RESET}{C.GREEN if state.confirmed else C.RED}{state.confirmed}{C.RESET}")
    print(f"  {C.DIM}blocking     {C.RESET}{C.YELLOW if blocking_count else C.GREEN}{blocking_count}{C.RESET}")

    divider("·")
    print(f"  {C.BOLD}Extracted Fields{C.RESET}")
    fields = state.fields.model_dump()
    missing_slots = set(state.missing)
    for field, value in fields.items():
        if field in missing_slots or value is None or value == []:
            print(f"  {C.DIM}  {field:<14} ✗  missing{C.RESET}")
        else:
            print(f"  {C.GREEN}  {field:<14} ✓{C.RESET}  {_fmt_value(value)}")

    divider("·")
    if state.missing:
        print(f"  {C.DIM}missing      {C.RESET}{C.YELLOW}{', '.join(state.missing)}{C.RESET}")
    else:
        print(f"  {C.DIM}missing      {C.RESET}{C.GREEN}none — all required fields collected{C.RESET}")

    if state.guideline_violations:
        print(f"  {C.DIM}compliance   {C.RESET}{C.YELLOW}{len(state.guideline_violations)} open issue(s){C.RESET}")
        print(f"  {C.DIM}next issue   {C.RESET}{state.guideline_violations[0]}")
    else:
        print(f"  {C.DIM}compliance   {C.RESET}{C.GREEN}clear{C.RESET}")
    divider()
    print()


def print_welcome(*, session_id: str, run_dir: Path) -> None:
    divider("═")
    print(
        f"""
{C.CYAN}{C.BOLD}  CODEGEN POC — Full Pipeline Runner{C.RESET}
{C.DIM}  Conversation -> Compile IR -> Emit React (Ant Design){C.RESET}

  Session: {session_id}
  Run Dir: {run_dir}

  {C.DIM}Commands: 'quit' to exit | 'state' to print current state | 'help' for commands{C.RESET}
"""
    )
    divider("═")
    print()


def print_help() -> None:
    divider()
    print(f"  {C.BOLD}Commands{C.RESET}")
    print("  quit  Exit the runner.")
    print("  state Print the latest state snapshot.")
    print("  help  Print available commands.")
    divider()
    print()


def print_final_summary(summary: dict[str, Any]) -> None:
    header("  ✓ FULL PIPELINE COMPLETE", color=C.BG_GREEN)
    divider()
    print(f"  {C.DIM}session_id   {C.RESET}{summary['session_id']}")
    print(f"  {C.DIM}run_dir      {C.RESET}{summary['run_dir']}")
    print(f"  {C.DIM}ui_plan      {C.RESET}{summary['ui_plan_path']}")
    print(f"  {C.DIM}compiled_ir  {C.RESET}{summary['compiled_ir_path']}")
    print(f"  {C.DIM}page_tsx     {C.RESET}{summary['page_path']}")
    print(f"  {C.DIM}compat_tsx   {C.RESET}{summary['compat_page_path']}")
    print(
        f"  {C.DIM}audit        {C.RESET}engine={summary['audit_engine']} "
        f"blocked={summary['audit_blocked']}"
    )
    divider()
    print()


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
            print_user_prompt()
            text = input().strip()
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
    interactive_mode = scripted_inputs is None

    if interactive_mode:
        print_welcome(session_id=session_id, run_dir=run_dir)
    else:
        print(f"session_id={session_id}")
        print(f"run_dir={run_dir}")
        print(f"mode=scripted inputs={len(scripted_inputs)} auto_confirm={args.auto_confirm}")

    while turn < args.max_turns:
        user_input, scripted_index = _next_input(
            state=state,
            scripted=scripted_inputs,
            index=scripted_index,
            auto_confirm=args.auto_confirm,
        )

        if user_input is None:
            if interactive_mode:
                print(f"\n  {C.DIM}Input interrupted or exhausted.{C.RESET}\n")
            else:
                print("input_exhausted=true")
            break

        user_input = user_input.strip()
        if not user_input:
            if scripted_inputs is not None:
                continue
            continue

        normalized = user_input.lower()
        if normalized == "quit":
            if interactive_mode:
                print(f"\n  {C.DIM}Exiting pipeline runner.{C.RESET}\n")
            else:
                print("quit_received=true")
            break
        if interactive_mode and normalized == "help":
            print_help()
            continue
        if interactive_mode and normalized == "state":
            gate = evaluate_quality_gate(
                state.fields,
                gate_mode=settings.quality_gate_mode,
            )
            print_state_snapshot(state, blocking_count=len(gate.blocking_findings))
            continue

        state.add_message("user", user_input)
        state = _as_state(await graph.ainvoke(state))
        save_session(session_id, state)

        assistant = _last_assistant_message(state)
        gate = evaluate_quality_gate(
            state.fields,
            gate_mode=settings.quality_gate_mode,
        )

        turn += 1
        if interactive_mode:
            if assistant:
                print_assistant(assistant, agent=state.active_agent or "Assistant")
            print_state_snapshot(state, blocking_count=len(gate.blocking_findings))
        else:
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
        if interactive_mode:
            header("  PIPELINE INCOMPLETE", color=C.BG_DARK)
            divider()
            print("  Conversation did not reach done mode before input/turn limit.")
            print(f"  Transcript saved: {run_dir / 'transcript.json'}")
            divider()
            print()
        else:
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
        if interactive_mode:
            header("  COMPILE FAILED", color=C.BG_DARK)
            divider()
            print(f"  http_status: {exc.status_code}")
            print(f"  detail: {exc.detail}")
            print(f"  error_file: {run_dir / 'compile_error.json'}")
            divider()
            print()
        else:
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
        if interactive_mode:
            header("  EMIT FAILED", color=C.BG_DARK)
            divider()
            print(f"  http_status: {exc.status_code}")
            print(f"  detail: {exc.detail}")
            print(f"  error_file: {run_dir / 'emit_error.json'}")
            divider()
            print()
        else:
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

    if interactive_mode:
        print_final_summary(summary)
    else:
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

# scripts/run_conversation.py

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.conversation.graph import build_graph
from backend.agents.conversation.models import ConversationState, UIPlan
from backend.core.logger import get_logger

logger = get_logger(__name__)


# ── Terminal colours ──────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Text colours
    WHITE   = "\033[97m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"

    # Background
    BG_DARK  = "\033[40m"
    BG_NAVY  = "\033[44m"


# ── Display helpers ───────────────────────────────────────────────────────────

WIDTH = 72


def _as_state(value: ConversationState | dict) -> ConversationState:
    if isinstance(value, ConversationState):
        return value
    return ConversationState.model_validate(value)

def divider(char="─", color=C.DIM):
    print(f"{color}{char * WIDTH}{C.RESET}")

def header(text: str, color=C.BG_NAVY):
    pad = WIDTH - len(text) - 4
    print(f"\n{color}{C.BOLD}  {text}{' ' * pad}  {C.RESET}")

def print_assistant(content: str, agent: str):
    print(f"\n{C.CYAN}{C.BOLD}  ● {agent}{C.RESET}")
    for line in content.splitlines():
        print(f"{C.CYAN}  │ {C.RESET}{line}")
    print()

def print_user_prompt():
    print(f"{C.GREEN}{C.BOLD}  You ›{C.RESET} ", end="", flush=True)


def _fmt_value(value) -> str:
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


def print_state(state: ConversationState):
    """
    Prints a structured view of the full ConversationState after each turn.
    """
    header("  STATE SNAPSHOT", color=C.BG_DARK)
    divider()

    # Mode + Agent
    mode_color = {
        "free_chat": C.YELLOW,
        "fill_gaps": C.MAGENTA,
        "confirm":   C.CYAN,
        "done":      C.GREEN,
    }.get(state.mode, C.WHITE)

    print(f"  {C.DIM}mode         {C.RESET}{mode_color}{C.BOLD}{state.mode}{C.RESET}")
    print(f"  {C.DIM}active_agent {C.RESET}{C.WHITE}{state.active_agent or '—'}{C.RESET}")
    print(f"  {C.DIM}turns        {C.RESET}{C.WHITE}{state.free_chat_turns()}{C.RESET}")
    print(f"  {C.DIM}confirmed    {C.RESET}{C.GREEN if state.confirmed else C.RED}{state.confirmed}{C.RESET}")

    divider("·")

    # Extracted fields
    print(f"  {C.BOLD}Extracted Fields{C.RESET}")
    fields = state.fields.model_dump()
    missing_slots = set(state.missing)
    for field, value in fields.items():
        if field in missing_slots or value is None or value == []:
            print(f"  {C.DIM}  {field:<12} ✗  missing{C.RESET}")
        else:
            print(f"  {C.GREEN}  {field:<12} ✓{C.RESET}  {_fmt_value(value)}")

    divider("·")

    # Missing fields
    if state.missing:
        missing_str = ", ".join(state.missing)
        print(f"  {C.DIM}missing      {C.RESET}{C.YELLOW}{missing_str}{C.RESET}")
    else:
        print(f"  {C.DIM}missing      {C.RESET}{C.GREEN}none — all fields collected{C.RESET}")

    if state.guideline_violations:
        print(f"  {C.DIM}compliance   {C.RESET}{C.YELLOW}{len(state.guideline_violations)} open issue(s){C.RESET}")
        print(f"  {C.DIM}next issue   {C.RESET}{state.guideline_violations[0]}")
    else:
        print(f"  {C.DIM}compliance   {C.RESET}{C.GREEN}clear{C.RESET}")

    divider()
    print()


def print_ui_plan(plan: UIPlan):
    """
    Prints the final confirmed UIPlan before handing off to IR compiler.
    """
    header("  ✓ UIPLAN CONFIRMED — READY FOR IR COMPILER", color="\033[42m\033[30m")
    divider()
    # Render a clean snapshot: omit unset optional keys instead of printing nulls.
    data = plan.model_dump(exclude_none=True)
    for field, value in data.items():
        print(f"  {C.BOLD}{C.GREEN}{field:<12}{C.RESET}  {_fmt_value(value)}")
    divider()
    print(f"\n  {C.DIM}Next step → ir_compiler.compile(ui_plan){C.RESET}\n")


def print_welcome():
    divider("═")
    print(f"""
{C.CYAN}{C.BOLD}  CODEGEN POC — Requirement Gathering{C.RESET}
{C.DIM}  Schema-Aware Conversational UI Code Generation{C.RESET}

  Describe your page in plain language.
  The system will extract: goal, layout, entities, actions, feedback, style.

  {C.DIM}Commands:  'quit' to exit  |  'state' to print current state{C.RESET}
""")
    divider("═")
    print()


# ── Main conversation loop ────────────────────────────────────────────────────

async def run():
    print_welcome()

    graph = build_graph()
    state = ConversationState()

    while True:
        # ── Get user input ────────────────────────────────────────────────────
        print_user_prompt()
        try:
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {C.DIM}Interrupted.{C.RESET}\n")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            print(f"\n  {C.DIM}Exiting.{C.RESET}\n")
            break

        if user_input.lower() == "state":
            print_state(state)
            continue

        # ── Append user message ───────────────────────────────────────────────
        state.add_message("user", user_input)

        # ── Run graph ─────────────────────────────────────────────────────────
        try:
            state = _as_state(await graph.ainvoke(state))
        except Exception as e:
            print(f"\n  {C.RED}Graph error: {e}{C.RESET}\n")
            logger.error("Graph error: %s", e)
            continue

        # ── Print assistant response ──────────────────────────────────────────
        last_msg = next(
            (m for m in reversed(state.messages) if m.role == "assistant"),
            None,
        )
        if last_msg:
            print_assistant(last_msg.content, agent=state.active_agent or "Assistant")

        # ── Print state snapshot after every turn ─────────────────────────────
        print_state(state)

        # ── Done ──────────────────────────────────────────────────────────────
        if state.mode == "done":
            ui_plan = UIPlan.from_spec(state.fields)
            print_ui_plan(ui_plan)

            # Optionally write UIPlan to file for inspection
            output_path = "ui_plan.json"
            with open(output_path, "w") as f:
                json.dump(ui_plan.model_dump(exclude_none=True), f, indent=2)
            print(f"  {C.DIM}UIPlan saved to {output_path}{C.RESET}\n")
            break


if __name__ == "__main__":
    asyncio.run(run())

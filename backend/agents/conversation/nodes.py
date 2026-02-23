# agents/conversation/nodes.py

from backend.core.logger import get_logger
from .models     import ConversationState, UIPlan
from .agents     import AGENTS
from .prompts    import (
    CONVERSATIONALIST_SYSTEM, EXTRACTOR_SYSTEM,
    INTERVIEWER_SYSTEM, SUMMARISER_SYSTEM, FIELD_QUESTIONS,
)

import json

ALL_FIELDS = ["goal", "layout", "entities", "actions", "feedback", "style"]


# ── NODE 1: chat_node — Conversationalist ─────────────────────────────────────
def chat_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["conversationalist"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    logger.info("Responding to user (turn %d)", state.free_chat_turns())

    response = agent.model.invoke([
        {"role": "system", "content": CONVERSATIONALIST_SYSTEM},
        *state.to_lc_messages(),
    ])

    state.add_message("assistant", response.content)
    logger.debug("Response: %s", response.content[:80])
    return state


# ── NODE 2: extractor_node — Extractor ───────────────────────────────────────
def extractor_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["extractor"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    logger.info("Extracting fields from conversation")

    response = agent.model.invoke([
        {"role": "system", "content": EXTRACTOR_SYSTEM},
        *state.to_lc_messages(),
    ])

    newly_extracted = []
    try:
        extracted = json.loads(response.content)
        for field, value in extracted.items():
            if value is not None and getattr(state.fields, field) is None:
                setattr(state.fields, field, value)
                newly_extracted.append(field)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse extractor JSON: %s", e)

    if newly_extracted:
        logger.info("Extracted: %s", ", ".join(newly_extracted))
    else:
        logger.debug("No new fields extracted")

    return state


# ── NODE 3: gap_check_node — Gap Finder ──────────────────────────────────────
def gap_check_node(state: ConversationState) -> ConversationState:
    from backend.core.setting import get_settings
    agent    = AGENTS["gap_finder"]
    logger   = get_logger(__name__, agent=agent.name)
    settings = get_settings()
    state.active_agent = agent.name

    prev_mode = state.mode

    if (
        state.free_chat_turns() >= settings.free_chat_turn_threshold
        and state.missing
        and state.mode == "free_chat"
    ):
        state.mode = "fill_gaps"

    state.current_gap = state.missing[0] if state.missing else None

    logger.info(
        "Missing: [%s] | Mode: %s%s",
        ", ".join(state.missing) if state.missing else "none",
        state.mode,
        f" (switched from {prev_mode})" if state.mode != prev_mode else "",
    )

    return state


# ── NODE 4: fill_gap_node — Interviewer ──────────────────────────────────────
def fill_gap_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["interviewer"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    field    = state.missing[0]
    question = FIELD_QUESTIONS[field]
    filled   = [f for f in ALL_FIELDS if getattr(state.fields, f) is not None]

    logger.info("Asking for missing field: %s", field)

    system = INTERVIEWER_SYSTEM.format(
        filled_fields = ", ".join(filled) if filled else "nothing yet",
        missing_field = field,
        base_question = question,
    )

    response = agent.model.invoke([
        {"role": "system", "content": system},
        *state.to_lc_messages(),
    ])

    state.add_message("assistant", response.content)
    logger.debug("Question asked: %s", response.content[:80])
    return state


# ── NODE 5: confirm_node — Summariser ────────────────────────────────────────
def confirm_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["summariser"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    logger.info("All fields collected — showing summary to user")

    f = state.fields
    summary = SUMMARISER_SYSTEM.format(
        goal     = f.goal,
        layout   = f.layout,
        entities = ", ".join(f.entities) if f.entities else "—",
        actions  = ", ".join(f.actions)  if f.actions  else "—",
        feedback = ", ".join(f.feedback) if f.feedback else "—",
        style    = f.style,
    )

    state.add_message("assistant", summary)
    state.mode = "confirm"
    return state


# ── NODE 6: done_node — Dispatcher ───────────────────────────────────────────
def done_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["dispatcher"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    state.confirmed = True
    state.mode      = "done"

    ui_plan = UIPlan.from_fields(state.fields)

    logger.info("UIPlan confirmed — dispatching to IR compiler")
    logger.debug("UIPlan: %s", ui_plan.model_dump_json(indent=2))

    # ir_compiler.compile(ui_plan)

    state.add_message("assistant", "All set! Generating your UI now…")
    return state

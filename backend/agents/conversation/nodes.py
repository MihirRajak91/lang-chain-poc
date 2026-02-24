# backend/agents/conversation/nodes.py

import json
from backend.core.logger import get_logger
from .models import ConversationState, UIPlan
from .agents  import AGENTS
from .prompts import (
    CONVERSATIONALIST_SYSTEM,
    EXTRACTOR_SYSTEM,
    INTERVIEWER_SYSTEM,
    SUMMARISER_SYSTEM,
    FIELD_QUESTIONS,
)

# Maps conversation field names → RequirementSpec slot names
FIELD_TO_SLOT = {
    "goal":         "page_goal",
    "layout":       "layout_zones",
    "entities":     "entities",
    "actions":      "actions",
    "feedback":     "feedback",
    "style":        "style",
}


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
    logger.debug("Response preview: %s", response.content[:100])
    return state


# ── NODE 2: extractor_node — Extractor ───────────────────────────────────────
def extractor_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["extractor"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    logger.info("Extracting fields from conversation")

    recent_messages = _get_recent_messages(state, n_user_turns=2)

    response = agent.model.invoke([
        {"role": "system", "content": EXTRACTOR_SYSTEM},
        *recent_messages,
    ])

    raw = _strip_fences(response.content)

    try:
        extracted = json.loads(raw)
        if not isinstance(extracted, dict):
            logger.warning("Extractor output was not a JSON object — skipping")
            return state

        updated = _merge_into_spec(state, extracted, logger)

        if updated:
            logger.info("Updated slots: %s", ", ".join(updated))
        else:
            logger.debug("No new slots updated this turn")

    except json.JSONDecodeError as e:
        logger.warning("Extractor JSON parse failed: %s | raw: %.120s", e, raw)

    return state


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
        raw = "\n".join(inner)
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _get_recent_messages(state: ConversationState, n_user_turns: int = 2) -> list[dict]:
    messages = state.to_lc_messages()
    user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if not user_indices:
        return messages
    cutoff = user_indices[-min(n_user_turns, len(user_indices))]
    return messages[cutoff:]


def _merge_into_spec(
    state: ConversationState, extracted: dict, logger
) -> list[str]:
    """
    Routes each extracted field into the correct RequirementSpec slot.
    Returns list of slot names that were updated.
    """
    spec    = state.fields
    updated = []

    # ── page_goal ─────────────────────────────────────────────────────────────
    goal = extracted.get("goal")
    if goal and isinstance(goal, str) and goal.strip():
        if spec.page_goal != goal.strip():
            spec.page_goal = goal.strip()
            spec.update_slot_status("page_goal", "complete")
            updated.append("page_goal")
            logger.debug("  page_goal → %s", spec.page_goal)

    # ── layout_zones ──────────────────────────────────────────────────────────
    layout = extracted.get("layout")
    if layout:
        try:
            zones_raw = layout if isinstance(layout, list) else _parse_layout(layout)
            changed = spec.merge_layout_zones(zones_raw)
            if changed:
                spec.update_slot_status("layout_zones", "complete")
                updated.append("layout_zones")
                logger.debug("  layout_zones → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge layout_zones: %s", exc)
            spec.update_slot_status("layout_zones", "uncertain", 0.0)

    # ── entities ──────────────────────────────────────────────────────────────
    entities = extracted.get("entities")
    if entities:
        try:
            entities_raw = entities if isinstance(entities, list) else []
            changed = spec.merge_entities(entities_raw)
            if changed:
                spec.update_slot_status("entities", "complete")
                updated.append("entities")
                logger.debug("  entities → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge entities: %s", exc)
            spec.update_slot_status("entities", "uncertain", 0.0)

    # ── actions ───────────────────────────────────────────────────────────────
    actions = extracted.get("actions")
    if actions:
        try:
            actions_raw = actions if isinstance(actions, list) else []
            changed = spec.merge_actions(actions_raw)
            if changed:
                spec.update_slot_status("actions", "complete")
                updated.append("actions")
                logger.debug("  actions → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge actions: %s", exc)
            spec.update_slot_status("actions", "uncertain", 0.0)

    # ── feedback ──────────────────────────────────────────────────────────────
    feedback = extracted.get("feedback")
    if feedback:
        try:
            feedback_raw = feedback if isinstance(feedback, list) else []
            changed = spec.merge_feedback(feedback_raw)
            if changed:
                spec.update_slot_status("feedback", "complete")
                updated.append("feedback")
                logger.debug("  feedback → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge feedback: %s", exc)
            spec.update_slot_status("feedback", "uncertain", 0.0)

    # ── style ─────────────────────────────────────────────────────────────────
    style = extracted.get("style")
    if style and isinstance(style, dict):
        try:
            changed = spec.merge_style(style)
            if changed:
                spec.update_slot_status("style", "complete")
                updated.append("style")
                logger.debug("  style → %s", style)
        except Exception as exc:
            logger.warning("Failed to merge style: %s", exc)
            spec.update_slot_status("style", "uncertain", 0.0)

    return updated


def _parse_layout(raw: str) -> list[dict]:
    """
    Converts a plain string layout description into a list of zone dicts.
    Used when the extractor returns layout as a string instead of structured list.
    Example: "Table at bottom-right, button centered"
    → [{"zone_id": "zone_table", "component": "DataTable", "anchor": "bottom-right"},
       {"zone_id": "zone_button", "component": "PrimaryButton", "anchor": "center"}]
    This is a best-effort parse — the extractor prompt should return structured data.
    """
    text = raw.lower()
    component = "Unknown"
    if "table" in text:
        component = "DataTable"
    elif "button" in text:
        component = "PrimaryButton"
    elif "modal" in text or "popup" in text or "dialog" in text:
        component = "Modal"

    anchor = None
    anchor_map = {
        "bottom-right": ["bottom-right", "bottom right"],
        "bottom-left": ["bottom-left", "bottom left"],
        "top-right": ["top-right", "top right"],
        "top-left": ["top-left", "top left"],
        "center": ["center", "centered", "middle"],
        "full-width": ["full-width", "full width"],
    }
    for normalized, variants in anchor_map.items():
        if any(v in text for v in variants):
            anchor = normalized
            break

    zone_id = "zone_main" if component == "Unknown" else f"zone_{component.lower()}"

    return [{
        "zone_id":   zone_id,
        "component": component,
        "anchor":    anchor,
        "notes":     raw,
    }]


# ── NODE 3: gap_check_node — Gap Finder (no LLM) ─────────────────────────────
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

    # Map slot name back to conversation field name for the question lookup
    slot    = state.missing[0]
    field   = next((k for k, v in FIELD_TO_SLOT.items() if v == slot), slot)
    question = FIELD_QUESTIONS.get(field, FIELD_QUESTIONS.get(slot, "Can you tell me more?"))

    missing_slots = set(state.missing)
    filled_slots = [k for k, mapped in FIELD_TO_SLOT.items() if mapped not in missing_slots]
    filled_str    = ", ".join(filled_slots) if filled_slots else "nothing yet"

    logger.info("Asking for missing slot: %s", slot)

    system = INTERVIEWER_SYSTEM.format(
        filled_fields = filled_str,
        missing_field = field,
        base_question = question,
    )

    response = agent.model.invoke([
        {"role": "system", "content": system},
        *state.to_lc_messages(),
    ])

    state.add_message("assistant", response.content)
    logger.debug("Question: %s", response.content[:100])
    return state


# ── NODE 5: confirm_node — Summariser ────────────────────────────────────────
def confirm_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["summariser"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    logger.info("All slots filled — showing summary")

    # Use RequirementSpec.summary() for rich formatted output
    spec_summary = state.fields.summary()

    summary = SUMMARISER_SYSTEM.format(spec_summary=spec_summary)

    state.add_message("assistant", summary)
    state.mode = "confirm"
    return state


# ── NODE 6: done_node — Dispatcher (no LLM) ──────────────────────────────────
def done_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["dispatcher"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    state.confirmed = True
    state.mode      = "done"

    # Build typed UIPlan from RequirementSpec — no string flattening
    ui_plan = UIPlan.from_spec(state.fields)

    logger.info("UIPlan confirmed — dispatching to IR compiler")
    logger.debug("UIPlan:\n%s", ui_plan.model_dump_json(indent=2))

    # ← Handoff to IR compiler
    # ir_compiler.compile(ui_plan)

    state.add_message("assistant", "All set! Generating your UI now…")
    return state

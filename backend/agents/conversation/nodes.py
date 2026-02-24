# backend/agents/conversation/nodes.py

from backend.core.logger import get_logger
from .models import ConversationState, UIPlan
from .agents  import AGENTS
from .parsing import parse_json_object_with_fallback, strip_json_fences
from .prompts import (
    CONVERSATIONALIST_SYSTEM,
    EXTRACTOR_SYSTEM,
    INTERVIEWER_SYSTEM,
    SUMMARISER_SYSTEM,
    FIELD_QUESTIONS,
)
from .routers import is_confirmation_message
from .validators import evaluate_quality_gate
from backend.design.recommender import recommend_design_defaults

EXTRACTOR_PARSE_MAX_ATTEMPTS = 2
EXTRACTOR_RETRY_INSTRUCTION = """
IMPORTANT:
- Return exactly one valid JSON object.
- Do not wrap output in markdown fences.
- Do not include commentary.
- Use null for unknown fields.
- Never leave trailing commas.
""".strip()

# Maps conversation field names → RequirementSpec slot names
FIELD_TO_SLOT = {
    "goal":         "page_goal",
    "layout":       "layout_zones",
    "components":   "components",
    "entities":     "entities",
    "actions":      "actions",
    "feedback":     "feedback",
    "style":        "style",
    "accessibility":"accessibility",
    "constraints":  "constraints",
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

    if _should_skip_extractor(state):
        logger.info("Skipping extraction for confirmation-only turn in confirm mode")
        return state

    logger.info("Extracting fields from conversation")

    recent_messages = _get_recent_messages(state, n_user_turns=2)

    extracted = _extract_with_retry(agent, recent_messages, logger)
    if extracted is None:
        return state

    updated = _merge_into_spec(state, extracted, logger)

    if updated:
        logger.info("Updated slots: %s", ", ".join(updated))
    else:
        logger.debug("No new slots updated this turn")

    return state


def _latest_user_text(state: ConversationState) -> str:
    return next(
        (m.content for m in reversed(state.messages) if m.role == "user"),
        "",
    )


def _should_skip_extractor(state: ConversationState) -> bool:
    if state.mode != "confirm":
        return False
    last_user = _latest_user_text(state)
    return is_confirmation_message(last_user, strict=True)


def _strip_fences(raw: str) -> str:
    # Backward-compatible wrapper for legacy callers.
    return strip_json_fences(raw)


def _extract_with_retry(agent, recent_messages: list[dict], logger) -> dict | None:
    """
    Parse extractor JSON robustly.
    1) Try normal extractor prompt.
    2) Retry once with strict JSON-only instruction if parsing fails.
    """
    for attempt in range(1, EXTRACTOR_PARSE_MAX_ATTEMPTS + 1):
        system_prompt = EXTRACTOR_SYSTEM
        if attempt > 1:
            system_prompt = f"{EXTRACTOR_SYSTEM}\n\n{EXTRACTOR_RETRY_INSTRUCTION}"

        response = agent.model.invoke([
            {"role": "system", "content": system_prompt},
            *recent_messages,
        ])

        raw = _strip_fences(response.content)
        extracted = parse_json_object_with_fallback(raw)
        if extracted is not None:
            if attempt > 1:
                logger.info("Extractor JSON parse recovered on retry attempt %d", attempt)
            return extracted

        logger.warning(
            "Extractor JSON parse failed (attempt %d/%d) | raw: %.120s",
            attempt,
            EXTRACTOR_PARSE_MAX_ATTEMPTS,
            raw,
        )

    return None


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

    # ── components ────────────────────────────────────────────────────────────
    components = extracted.get("components")
    if components:
        try:
            components_raw = components if isinstance(components, list) else []
            changed = spec.merge_components(components_raw)
            if changed:
                spec.update_slot_status("components", "complete")
                updated.append("components")
                logger.debug("  components → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge components: %s", exc)
            spec.update_slot_status("components", "uncertain", 0.0)

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

    # ── product_context ──────────────────────────────────────────────────────
    product_context = extracted.get("product_context")
    if product_context and isinstance(product_context, dict):
        try:
            changed = spec.merge_product_context(product_context)
            if changed:
                spec.update_slot_status("product_context", "complete")
                updated.append("product_context")
                logger.debug("  product_context → %s", product_context)
        except Exception as exc:
            logger.warning("Failed to merge product_context: %s", exc)
            spec.update_slot_status("product_context", "uncertain", 0.0)

    # ── design_intent ────────────────────────────────────────────────────────
    design_intent = extracted.get("design_intent")
    if design_intent and isinstance(design_intent, dict):
        try:
            changed = spec.merge_design_intent(design_intent)
            if changed:
                spec.update_slot_status("design_intent", "complete")
                updated.append("design_intent")
                logger.debug("  design_intent → %s", design_intent)
        except Exception as exc:
            logger.warning("Failed to merge design_intent: %s", exc)
            spec.update_slot_status("design_intent", "uncertain", 0.0)

    # ── design_system ────────────────────────────────────────────────────────
    design_system = extracted.get("design_system")
    if design_system and isinstance(design_system, dict):
        try:
            changed = spec.merge_design_system(design_system)
            if changed:
                spec.update_slot_status("design_system", "complete")
                updated.append("design_system")
                logger.debug("  design_system → %s", design_system)
        except Exception as exc:
            logger.warning("Failed to merge design_system: %s", exc)
            spec.update_slot_status("design_system", "uncertain", 0.0)

    # ── accessibility ────────────────────────────────────────────────────────
    accessibility = extracted.get("accessibility")
    if accessibility and isinstance(accessibility, dict):
        try:
            changed = spec.merge_accessibility(accessibility)
            if changed:
                spec.update_slot_status("accessibility", "complete")
                updated.append("accessibility")
                logger.debug("  accessibility → %s", accessibility)
        except Exception as exc:
            logger.warning("Failed to merge accessibility: %s", exc)
            spec.update_slot_status("accessibility", "uncertain", 0.0)

    # ── constraints ──────────────────────────────────────────────────────────
    constraints = extracted.get("constraints")
    if constraints:
        try:
            constraints_raw = constraints if isinstance(constraints, list) else []
            changed = spec.merge_constraints(constraints_raw)
            if changed:
                spec.update_slot_status("constraints", "complete")
                updated.append("constraints")
                logger.debug("  constraints → %s", changed)
        except Exception as exc:
            logger.warning("Failed to merge constraints: %s", exc)
            spec.update_slot_status("constraints", "uncertain", 0.0)

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

    if settings.design_intel_enabled:
        snapshot = recommend_design_defaults(state.fields)
        state.recommendation_snapshot = snapshot.model_dump(exclude_none=True)
        logger.debug(
            "Design recommendation snapshot refreshed: engine=%s",
            snapshot.engine,
        )
    else:
        state.recommendation_snapshot = {}

    seeded_components = state.fields.ensure_components_from_layout()
    if seeded_components:
        state.fields.update_slot_status("components", "complete")
        logger.debug(
            "Auto-seeded components from layout zones: %s",
            ", ".join(seeded_components),
        )

    gate_mode = getattr(settings, "quality_gate_mode", "hybrid")
    gate = evaluate_quality_gate(state.fields, gate_mode=gate_mode)
    state.guideline_violations = [issue.message for issue in gate.blocking_findings]

    if state.missing:
        if (
            state.free_chat_turns() >= settings.free_chat_turn_threshold
            and state.mode == "free_chat"
        ):
            state.mode = "fill_gaps"
        state.current_gap = state.missing[0]
    elif gate.blocking_findings:
        state.mode = "fill_gaps"
        state.current_gap = gate.blocking_findings[0].slot
    else:
        if state.mode == "fill_gaps":
            state.mode = "free_chat"
        state.current_gap = None

    logger.info(
        "Missing: [%s] | Critical: %d | Warnings: %d | Blocking: %d | Gate: %s | Mode: %s%s",
        ", ".join(state.missing) if state.missing else "none",
        len(gate.critical_violations),
        len(gate.warning_findings),
        len(gate.blocking_findings),
        gate.gate_mode,
        state.mode,
        f" (switched from {prev_mode})" if state.mode != prev_mode else "",
    )

    return state


# ── NODE 4: fill_gap_node — Interviewer ──────────────────────────────────────
def fill_gap_node(state: ConversationState) -> ConversationState:
    agent  = AGENTS["interviewer"]
    logger = get_logger(__name__, agent=agent.name)
    state.active_agent = agent.name

    # Choose missing required slot first; then unresolved compliance question.
    if state.missing:
        slot = state.missing[0]
    else:
        slot = state.current_gap or "constraints"

    field   = next((k for k, v in FIELD_TO_SLOT.items() if v == slot), slot)
    question = FIELD_QUESTIONS.get(field, FIELD_QUESTIONS.get(slot, "Can you tell me more?"))
    if not state.missing and state.guideline_violations:
        question = state.guideline_violations[0]

    missing_slots = set(state.missing)
    if not state.missing and state.current_gap:
        missing_slots.add(state.current_gap)
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

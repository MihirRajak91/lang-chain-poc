# api/websocket.py

import uuid
from fastapi             import APIRouter, WebSocket, WebSocketDisconnect
from backend.agents.conversation.models import ConversationState
from backend.core.logger import get_logger
from backend.core.setting import get_settings
from backend.core.session import get_session, save_session, clear_session
from backend.agents.conversation.graph import build_graph
from backend.agents.conversation.validators import QualityGateEvaluation, evaluate_quality_gate

logger    = get_logger(__name__)
ws_router = APIRouter()

# Graph compiled once at startup — reused across all connections
graph = build_graph()


def _as_state(value: ConversationState | dict) -> ConversationState:
    if isinstance(value, ConversationState):
        return value
    return ConversationState.model_validate(value)


def _is_effectively_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


@ws_router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """
    Main conversation WebSocket.

    Client sends:
        { "session_id": "...", "message": "..." }
        session_id is optional — server generates one if not provided.

    Server sends back per turn:
        { "type": "message",      "content": "...",  "agent": "..." }
        { "type": "field_update", "field": "...",    "value": "..." }
        { "type": "quality_finding", ... }
        { "type": "spec_snapshot", ... }
        { "type": "mode_change",  "mode": "...",               }
        { "type": "done",         "ui_plan": { ... }            }
        { "type": "error",        "detail": "..."               }
    """
    await websocket.accept()
    session_id = None

    try:
        while True:
            # ── Receive ───────────────────────────────────────────────────────
            data = await websocket.receive_json()

            session_id = data.get("session_id") or str(uuid.uuid4())
            user_message = data.get("message", "").strip()

            if not user_message:
                await _send(websocket, {
                    "type":   "error",
                    "detail": "Empty message received",
                })
                continue

            logger.info(
                "WS message received | session: %s | turn: %d",
                session_id,
                _count_turns(session_id) + 1,
            )

            # ── Load state ────────────────────────────────────────────────────
            state = get_session(session_id)
            prev_fields = state.fields.model_dump()
            prev_mode   = state.mode
            settings = get_settings()
            prev_gate = evaluate_quality_gate(
                state.fields,
                gate_mode=settings.quality_gate_mode,
            )

            # ── Append user message ───────────────────────────────────────────
            state.add_message("user", user_message)

            # ── Run graph ─────────────────────────────────────────────────────
            try:
                state = _as_state(await graph.ainvoke(state))
            except Exception as e:
                logger.error("Graph error for session %s: %s", session_id, e)
                await _send(websocket, {
                    "type":   "error",
                    "detail": f"Agent error: {str(e)}",
                })
                continue

            # ── Persist ───────────────────────────────────────────────────────
            save_session(session_id, state)

            # ── Send assistant message ────────────────────────────────────────
            last_msg = next(
                (m for m in reversed(state.messages) if m.role == "assistant"),
                None,
            )
            if last_msg:
                await _send(websocket, {
                    "type":       "message",
                    "session_id": session_id,
                    "content":    last_msg.content,
                    "agent":      state.active_agent,
                })

            # ── Send field updates (changed extracted fields) ──────────────────
            current_fields = state.fields.model_dump()
            for field, value in current_fields.items():
                prev_value = prev_fields.get(field)
                if value != prev_value and not _is_effectively_empty(value):
                    await _send(websocket, {
                        "type":  "field_update",
                        "field": field,
                        "value": value,
                    })
                    logger.debug(
                        "Field update sent | session: %s | %s = %s",
                        session_id, field, value,
                    )

            # ── Send quality finding deltas ───────────────────────────────────
            current_gate = evaluate_quality_gate(
                state.fields,
                gate_mode=settings.quality_gate_mode,
            )
            for finding_event in _build_quality_finding_events(
                session_id=session_id,
                previous=prev_gate,
                current=current_gate,
            ):
                await _send(websocket, finding_event)

            # ── Send full per-turn spec snapshot ──────────────────────────────
            await _send(
                websocket,
                _build_spec_snapshot_payload(
                    session_id=session_id,
                    state=state,
                    gate=current_gate,
                ),
            )

            # ── Send mode change ──────────────────────────────────────────────
            if state.mode != prev_mode:
                await _send(websocket, {
                    "type": "mode_change",
                    "mode": state.mode,
                })
                logger.info(
                    "Mode change | session: %s | %s → %s",
                    session_id, prev_mode, state.mode,
                )

            # ── Done — emit UIPlan and close ──────────────────────────────────
            if state.mode == "done":
                from backend.agents.conversation.models import UIPlan
                ui_plan = UIPlan.from_spec(state.fields)

                await _send(websocket, {
                    "type":       "done",
                    "session_id": session_id,
                    "ui_plan":    ui_plan.model_dump(exclude_none=True),
                })

                logger.info(
                    "Conversation complete | session: %s | closing WebSocket",
                    session_id,
                )
                clear_session(session_id)
                await websocket.close()
                break

    except WebSocketDisconnect:
        logger.info("WS disconnected | session: %s", session_id or "unknown")

    except Exception as e:
        logger.error("WS fatal error | session: %s | %s", session_id or "unknown", e)
        try:
            await _send(websocket, {"type": "error", "detail": str(e)})
            await websocket.close()
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send(websocket: WebSocket, payload: dict) -> None:
    """Safe send — logs and swallows send errors."""
    try:
        await websocket.send_json(payload)
    except Exception as e:
        logger.warning("Failed to send WS payload: %s", e)


def _count_turns(session_id: str) -> int:
    from backend.core.session import session_exists
    if not session_exists(session_id):
        return 0
    from backend.core.session import get_session as _gs
    return _gs(session_id).free_chat_turns()


def _issue_key(issue) -> tuple[str, str, str]:
    return (issue.severity, issue.slot, issue.message)


def _build_quality_finding_events(
    session_id: str,
    previous: QualityGateEvaluation,
    current: QualityGateEvaluation,
) -> list[dict]:
    prev_map = {_issue_key(item): item for item in [*previous.critical_violations, *previous.warning_findings]}
    curr_map = {_issue_key(item): item for item in [*current.critical_violations, *current.warning_findings]}
    prev_blocking = {_issue_key(item) for item in previous.blocking_findings}
    curr_blocking = {_issue_key(item) for item in current.blocking_findings}

    payloads: list[dict] = []

    for key in sorted(curr_map.keys() - prev_map.keys()):
        severity, slot, message = key
        payloads.append(
            {
                "type": "quality_finding",
                "session_id": session_id,
                "status": "open",
                "severity": severity,
                "slot": slot,
                "message": message,
                "blocking": key in curr_blocking,
                "gate_mode": current.gate_mode,
            }
        )

    for key in sorted(prev_map.keys() - curr_map.keys()):
        severity, slot, message = key
        payloads.append(
            {
                "type": "quality_finding",
                "session_id": session_id,
                "status": "resolved",
                "severity": severity,
                "slot": slot,
                "message": message,
                "blocking": key in prev_blocking,
                "gate_mode": current.gate_mode,
            }
        )

    return payloads


def _build_spec_snapshot_payload(
    session_id: str,
    state: ConversationState,
    gate: QualityGateEvaluation,
) -> dict:
    return {
        "type": "spec_snapshot",
        "session_id": session_id,
        "mode": state.mode,
        "missing": state.missing,
        "spec": state.fields.model_dump(exclude_none=True),
        "quality": {
            "gate_mode": gate.gate_mode,
            "is_blocked": gate.is_blocked,
            "critical_count": len(gate.critical_violations),
            "warning_count": len(gate.warning_findings),
            "blocking_count": len(gate.blocking_findings),
            "critical_violations": [item.message for item in gate.critical_violations],
            "warning_findings": [item.message for item in gate.warning_findings],
            "blocking_findings": [item.message for item in gate.blocking_findings],
        },
        "guideline_violations": state.guideline_violations,
        "recommendation_snapshot": state.recommendation_snapshot,
    }

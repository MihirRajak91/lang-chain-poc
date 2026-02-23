# api/websocket.py

import uuid
from fastapi             import APIRouter, WebSocket, WebSocketDisconnect
from backend.agents.conversation.models import ConversationState
from backend.core.logger import get_logger
from backend.core.session import get_session, save_session, clear_session
from backend.agents.conversation.graph import build_graph

logger    = get_logger(__name__)
ws_router = APIRouter()

# Graph compiled once at startup — reused across all connections
graph = build_graph()


def _as_state(value: ConversationState | dict) -> ConversationState:
    if isinstance(value, ConversationState):
        return value
    return ConversationState.model_validate(value)


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

            # ── Send field updates (newly extracted fields) ───────────────────
            current_fields = state.fields.model_dump()
            for field, value in current_fields.items():
                if value is not None and prev_fields.get(field) is None:
                    await _send(websocket, {
                        "type":  "field_update",
                        "field": field,
                        "value": value,
                    })
                    logger.debug(
                        "Field update sent | session: %s | %s = %s",
                        session_id, field, value,
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
                ui_plan = UIPlan.from_fields(state.fields)

                await _send(websocket, {
                    "type":       "done",
                    "session_id": session_id,
                    "ui_plan":    ui_plan.model_dump(),
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

# core/session.py

from backend.agents.conversation.models import ConversationState
from backend.core.logger import get_logger

logger = get_logger(__name__)

# In-memory store — keyed by session_id
_sessions: dict[str, ConversationState] = {}


def get_session(session_id: str) -> ConversationState:
    """
    Returns existing session or creates a fresh one.
    """
    if session_id not in _sessions:
        logger.info("Creating new session: %s", session_id)
        _sessions[session_id] = ConversationState()
    return _sessions[session_id]


def save_session(session_id: str, state: ConversationState) -> None:
    """
    Persists updated state back to the store.
    """
    _sessions[session_id] = state
    logger.debug(
        "Session saved: %s | turns: %d | mode: %s | missing: [%s]",
        session_id,
        state.free_chat_turns(),
        state.mode,
        ", ".join(state.missing) if state.missing else "none",
    )


def clear_session(session_id: str) -> None:
    """
    Removes a session — called after done_node or on explicit reset.
    """
    if session_id in _sessions:
        _sessions.pop(session_id)
        logger.info("Session cleared: %s", session_id)


def session_exists(session_id: str) -> bool:
    return session_id in _sessions


def all_session_ids() -> list[str]:
    """Debug utility — lists all active sessions."""
    return list(_sessions.keys())

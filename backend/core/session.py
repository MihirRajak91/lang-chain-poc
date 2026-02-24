# core/session.py

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.agents.conversation.models import ConversationState
from backend.core.logger import get_logger

logger = get_logger(__name__)

# In-memory store — keyed by session_id
_sessions: dict[str, ConversationState] = {}
_compiled_irs: dict[str, dict] = {}
_LOGS_ROOT = Path(__file__).resolve().parents[2] / ".logs" / "sessions"


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
        clear_compiled_ir(session_id)
        logger.info("Session cleared: %s", session_id)


def session_exists(session_id: str) -> bool:
    return session_id in _sessions


def all_session_ids() -> list[str]:
    """Debug utility — lists all active sessions."""
    return list(_sessions.keys())


def save_compiled_ir(session_id: str, ir: dict) -> None:
    """Persists compiled IR bundle for a session."""
    _compiled_irs[session_id] = ir
    path = compiled_ir_log_path(session_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(ir, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        logger.info("Compiled IR saved: %s | path: %s", session_id, path)
    except OSError as exc:
        logger.warning("Failed to write compiled IR log for %s: %s", session_id, exc)


def get_compiled_ir(session_id: str) -> dict | None:
    """Returns compiled IR bundle if present."""
    return _compiled_irs.get(session_id)


def clear_compiled_ir(session_id: str) -> None:
    """Removes compiled IR bundle for a session."""
    _compiled_irs.pop(session_id, None)


def compiled_ir_log_path(session_id: str) -> Path:
    """Returns the stable log path for compiled IR artifact of a session."""
    safe_session = _sanitize_session_id(session_id)
    return _LOGS_ROOT / safe_session / "compiled_ir.json"


def _sanitize_session_id(session_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id.strip())
    return value or "session"

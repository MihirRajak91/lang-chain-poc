# agents/conversation/routers.py

from .models import ConversationState

CONFIRM_WORDS = {
    "yes", "correct", "looks good", "proceed",
    "go ahead", "perfect", "yep", "sure", "confirmed"
}

def _normalize_text(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return " ".join(cleaned.split())


_NORMALIZED_CONFIRM_WORDS = {_normalize_text(word) for word in CONFIRM_WORDS}


def is_confirmation_message(text: str, *, strict: bool = False) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if strict:
        return normalized in _NORMALIZED_CONFIRM_WORDS
    return any(word in normalized for word in _NORMALIZED_CONFIRM_WORDS)


def _is_confirmation(state: ConversationState) -> bool:
    last_user = next(
        (m.content.lower() for m in reversed(state.messages) if m.role == "user"),
        "",
    )
    return is_confirmation_message(last_user)


def route_after_gap_check(state: ConversationState) -> str:
    if state.mode == "confirm":
        return "done_node" if _is_confirmation(state) else "confirm_node"
    if state.mode == "fill_gaps":
        return "fill_gap_node"
    if not state.missing:
        return "confirm_node"
    return "chat_node"

def route_after_confirm(state: ConversationState) -> str:
    if _is_confirmation(state):
        return "done_node"
    return "chat_node"

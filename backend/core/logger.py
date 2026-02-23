# core/logger.py

import logging
import sys
from typing import Optional
from backend.core.setting import get_settings

settings = get_settings()

# ── Log format ────────────────────────────────────────────────────────────────
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | "
    "%(agent)-20s | %(message)s"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class AgentLoggerAdapter(logging.LoggerAdapter):
    """
    Wraps a standard logger and injects `agent` into every log record.
    Usage:
        logger = get_logger(__name__, agent="Extractor")
        logger.info("Parsing fields from message")
        # → 2026-02-23 10:00:00 | INFO     | agents.conversation.nodes     | Extractor            | Parsing fields from message
    """

    def process(self, msg: str, kwargs: dict) -> tuple:
        kwargs.setdefault("extra", {})
        kwargs["extra"]["agent"] = self.extra.get("agent", "—")
        return msg, kwargs


class AgentFilter(logging.Filter):
    """
    Ensures every log record has an `agent` field
    even if it wasn't set via AgentLoggerAdapter.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "agent"):
            record.agent = "—"
        return True


def _build_handler(stream=sys.stdout) -> logging.StreamHandler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler.addFilter(AgentFilter())
    return handler


def _configure_root_logger() -> None:
    """
    Called once at startup. Sets level from settings.
    All child loggers inherit this config.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    # Avoid duplicate handlers on reload (uvicorn --reload)
    if not root.handlers:
        root.addHandler(_build_handler())

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "langchain", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Public API ────────────────────────────────────────────────────────────────

def get_logger(name: str, agent: Optional[str] = None) -> logging.LoggerAdapter:
    """
    Returns a logger for the given module name.
    Optionally bind an agent name for structured output.

    Examples:
        # Module-level logger (no agent)
        logger = get_logger(__name__)

        # Node-level logger (with agent)
        logger = get_logger(__name__, agent="Extractor")
    """
    _configure_root_logger()
    base = logging.getLogger(name)
    return AgentLoggerAdapter(base, extra={"agent": agent or "—"})

# core/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

class AgentSettings(BaseSettings):
    """
    Loads all agent LLM config from .env.
    Each agent has its own model, temperature, and max_tokens.
    """

    _env_file = Path(__file__).resolve().parent.parent / ".env"

    model_config = SettingsConfigDict(
        env_file        = _env_file,
        env_file_encoding = "utf-8",
        case_sensitive  = False,
        extra           = "ignore",
    )

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    openai_api_key: str

    # ── Conversationalist ──────────────────────────────────────────────────────
    conversationalist_model:       str   = "gpt-4o"
    conversationalist_temperature: float = 0.7
    conversationalist_max_tokens:  int   = 1024

    # ── Extractor ──────────────────────────────────────────────────────────────
    extractor_model:               str   = "gpt-4o-mini"
    extractor_temperature:         float = 0.0
    extractor_max_tokens:          int   = 512

    # ── Interviewer ────────────────────────────────────────────────────────────
    interviewer_model:             str   = "gpt-4o"
    interviewer_temperature:       float = 0.6
    interviewer_max_tokens:        int   = 512

    # ── Summariser ─────────────────────────────────────────────────────────────
    summariser_model:              str   = "gpt-4o"
    summariser_temperature:        float = 0.3
    summariser_max_tokens:         int   = 1024

    # ── App behaviour ──────────────────────────────────────────────────────────
    free_chat_turn_threshold:      int   = 6

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: str = "INFO"   # DEBUG | INFO | WARNING | ERROR


@lru_cache()
def get_settings() -> AgentSettings:
    """
    Cached singleton — settings loaded once at startup.
    Call get_settings() anywhere; .env is only read once.
    """
    return AgentSettings()

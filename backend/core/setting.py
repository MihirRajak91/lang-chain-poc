# core/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Literal

class AgentSettings(BaseSettings):
    """
    Loads all agent LLM config from .env.
    Each agent has its own model, temperature, and max_tokens.
    """

    _env_file = Path(__file__).resolve().parents[2] / ".env"

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
    interviewer_paraphrase_enabled: bool = False

    # ── Summariser ─────────────────────────────────────────────────────────────
    summariser_model:              str   = "gpt-4o"
    summariser_temperature:        float = 0.3
    summariser_max_tokens:         int   = 1024

    # ── Emitter ────────────────────────────────────────────────────────────────
    emitter_model:                 str   = "gpt-4o"
    emitter_temperature:           float = 0.0
    emitter_max_tokens:            int   = 4096

    # ── App behaviour ──────────────────────────────────────────────────────────
    free_chat_turn_threshold:      int   = 6

    # ── Feature flags (Step 1: config-only, no behavior wiring yet) ─────────
    design_intel_enabled:          bool = True
    react_quality_audit_enabled:   bool = True
    quality_gate_mode:             Literal["hybrid", "hard", "advisory"] = "hybrid"
    knowledge_pack_version:        str = "v1-curated"

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: str = "INFO"   # DEBUG | INFO | WARNING | ERROR


@lru_cache()
def get_settings() -> AgentSettings:
    """
    Cached singleton — settings loaded once at startup.
    Call get_settings() anywhere; .env is only read once.
    """
    return AgentSettings()

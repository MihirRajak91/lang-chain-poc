# core/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field

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

    # ── LLM Provider Routing ───────────────────────────────────────────────────
    llm_primary_provider: Literal["bedrock", "openai"] = "bedrock"
    llm_fallback_provider: Literal["openai", "none"] = "openai"

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    openai_api_key: str | None = None

    # ── AWS / Bedrock ──────────────────────────────────────────────────────────
    aws_region: str | None = None
    aws_profile: str | None = None
    aws_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "aws_access_key_id", "aws_access_key"),
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key", "aws_secret_key"),
    )
    aws_session_token: str | None = None

    # ── Conversationalist ──────────────────────────────────────────────────────
    conversationalist_model:       str   = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    conversationalist_temperature: float = 0.7
    conversationalist_max_tokens:  int   = 1024

    # ── Extractor ──────────────────────────────────────────────────────────────
    extractor_model:               str   = "anthropic.claude-haiku-4-5-20251001-v1:0"
    extractor_temperature:         float = 0.0
    extractor_max_tokens:          int   = 512

    # ── Interviewer ────────────────────────────────────────────────────────────
    interviewer_model:             str   = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    interviewer_temperature:       float = 0.6
    interviewer_max_tokens:        int   = 512
    interviewer_paraphrase_enabled: bool = False

    # ── Summariser ─────────────────────────────────────────────────────────────
    summariser_model:              str   = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    summariser_temperature:        float = 0.3
    summariser_max_tokens:         int   = 1024

    # ── Emitter ────────────────────────────────────────────────────────────────
    emitter_model:                 str   = "anthropic.claude-sonnet-4-5-20250929-v1:0"
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

from __future__ import annotations

import logging
from typing import Literal

from backend.core.setting import AgentSettings

logger = logging.getLogger(__name__)

ProviderName = Literal["bedrock", "openai"]


def _openai_fallback_model(requested_model: str) -> str:
    """
    If Bedrock fails and fallback provider is OpenAI, Bedrock model IDs such as
    anthropic.* are not valid in OpenAI. Map to a safe default.
    """
    if requested_model.startswith("anthropic.claude-haiku"):
        return "gpt-4o-mini"
    if requested_model.startswith("anthropic."):
        return "gpt-4o"
    return requested_model


def _create_openai_model(
    *,
    model: str,
    temperature: float,
    max_tokens: int | None,
    settings: AgentSettings,
):
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, object] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    return ChatOpenAI(**kwargs)


def _create_bedrock_model(
    *,
    model: str,
    temperature: float,
    max_tokens: int | None,
    settings: AgentSettings,
):
    import boto3
    from langchain_aws import ChatBedrockConverse

    session_kwargs: dict[str, str] = {}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile
    if settings.aws_region:
        session_kwargs["region_name"] = settings.aws_region
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.aws_session_token:
        session_kwargs["aws_session_token"] = settings.aws_session_token

    session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()

    client_kwargs: dict[str, str] = {}
    if settings.aws_region:
        client_kwargs["region_name"] = settings.aws_region

    client = session.client("bedrock-runtime", **client_kwargs)
    return ChatBedrockConverse(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        client=client,
    )


def _create_model(
    *,
    provider: ProviderName,
    model: str,
    temperature: float,
    max_tokens: int | None,
    settings: AgentSettings,
):
    if provider == "bedrock":
        return _create_bedrock_model(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            settings=settings,
        )
    if provider == "openai":
        return _create_openai_model(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            settings=settings,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def build_chat_model(
    *,
    provider: ProviderName | None,
    model: str,
    temperature: float,
    max_tokens: int | None,
    settings: AgentSettings,
):
    """
    Provider-agnostic chat model factory.
    Primary provider comes from arg or settings.llm_primary_provider.
    If primary init fails and fallback=openai, fallback model is attempted.
    """
    primary: ProviderName = provider or settings.llm_primary_provider

    try:
        return _create_model(
            provider=primary,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            settings=settings,
        )
    except Exception as primary_exc:
        if primary == "openai" or settings.llm_fallback_provider != "openai":
            raise

        fallback_model = _openai_fallback_model(model)
        logger.warning(
            "Primary LLM provider failed (%s). Falling back to OpenAI model '%s'. Error: %s",
            primary,
            fallback_model,
            primary_exc,
        )
        return _create_openai_model(
            model=fallback_model,
            temperature=temperature,
            max_tokens=max_tokens,
            settings=settings,
        )

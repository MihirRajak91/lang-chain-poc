# agents/conversation/agents.py

from dataclasses import dataclass
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel

from backend.core.llm import build_chat_model
from backend.core.setting import get_settings

settings = get_settings()

@dataclass
class AgentConfig:
    name:        str
    description: str
    model:       Optional[BaseChatModel]   # None for logic-only nodes
    node:        str


def _llm(model: str, temperature: float, max_tokens: int) -> BaseChatModel:
    """
    Builds a provider-agnostic chat model from settings values.
    """
    return build_chat_model(
        provider     = settings.llm_primary_provider,
        model        = model,
        temperature  = temperature,
        max_tokens   = max_tokens,
        settings     = settings,
    )


AGENTS: dict[str, AgentConfig] = {

    "conversationalist": AgentConfig(
        name        = "Conversationalist",
        description = "Drives free-form conversation. Never asks for fields explicitly.",
        model       = _llm(
                        settings.conversationalist_model,
                        settings.conversationalist_temperature,
                        settings.conversationalist_max_tokens,
                      ),
        node        = "chat_node",
    ),

    "extractor": AgentConfig(
        name        = "Extractor",
        description = "Silently parses all 6 fields from the conversation history.",
        model       = _llm(
                        settings.extractor_model,
                        settings.extractor_temperature,
                        settings.extractor_max_tokens,
                      ),
        node        = "extractor_node",
    ),

    "gap_finder": AgentConfig(
        name        = "Gap Finder",
        description = "Checks which of the 6 fields are still missing. No LLM.",
        model       = None,
        node        = "gap_check_node",
    ),

    "interviewer": AgentConfig(
        name        = "Interviewer",
        description = "Asks for one missing field at a time in a natural tone.",
        model       = _llm(
                        settings.interviewer_model,
                        settings.interviewer_temperature,
                        settings.interviewer_max_tokens,
                      ),
        node        = "fill_gap_node",
    ),

    "summariser": AgentConfig(
        name        = "Summariser",
        description = "Renders structured summary of all 6 fields, asks to confirm.",
        model       = _llm(
                        settings.summariser_model,
                        settings.summariser_temperature,
                        settings.summariser_max_tokens,
                      ),
        node        = "confirm_node",
    ),

    "dispatcher": AgentConfig(
        name        = "Dispatcher",
        description = "Emits confirmed UIPlan to IR compiler pipeline. No LLM.",
        model       = None,
        node        = "done_node",
    ),
}

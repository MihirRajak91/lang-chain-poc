# agents/conversation/models.py

from __future__ import annotations
from typing    import Literal, Optional
from pydantic  import BaseModel, Field


# ── Extracted Fields ──────────────────────────────────────────────────────────

class ExtractedFields(BaseModel):
    """
    The 6 fields extracted from the conversation.
    Each maps directly to one sub-IR.
    """
    goal:     Optional[str]       = Field(None, description="What the page should accomplish")
    layout:   Optional[str]       = Field(None, description="Component placement on the page")
    entities: Optional[list[str]] = Field(None, description="Data tables or objects involved")
    actions:  Optional[list[str]] = Field(None, description="What the user can do on the page")
    feedback: Optional[list[str]] = Field(None, description="What happens after each action")
    style:    Optional[str]       = Field(None, description="Visual aesthetic preference")

    @property
    def missing_fields(self) -> list[str]:
        all_fields = ["goal", "layout", "entities", "actions", "feedback", "style"]
        return [f for f in all_fields if getattr(self, f) is None]

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0


# ── Conversation Message ──────────────────────────────────────────────────────

class Message(BaseModel):
    role:    Literal["user", "assistant", "system"]
    content: str


# ── Conversation State ────────────────────────────────────────────────────────

class ConversationState(BaseModel):
    """
    Full state passed between every graph node.
    active_agent is set at the top of each node for tracing.
    """
    messages:     list[Message]   = Field(default_factory=list)
    fields:       ExtractedFields = Field(default_factory=ExtractedFields)
    mode:         Literal[
                    "free_chat",
                    "fill_gaps",
                    "confirm",
                    "done"
                  ]               = "free_chat"
    current_gap:  Optional[str]   = None
    confirmed:    bool            = False
    active_agent: Optional[str]   = None

    @property
    def missing(self) -> list[str]:
        return self.fields.missing_fields

    def add_message(self, role: Literal["user", "assistant"], content: str) -> None:
        self.messages.append(Message(role=role, content=content))

    def to_lc_messages(self) -> list[dict]:
        """Convert to LangChain message format for LLM calls."""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def free_chat_turns(self) -> int:
        """Number of complete user+assistant turns so far."""
        return sum(1 for m in self.messages if m.role == "user")


# ── UIPlan (output of done_node → IR compiler input) ─────────────────────────

class UIPlan(BaseModel):
    """
    Final confirmed output of the conversation graph.
    Passed directly to ir_compiler.compile().
    """
    goal:     str
    layout:   str
    entities: list[str]
    actions:  list[str]
    feedback: list[str]
    style:    str

    @classmethod
    def from_fields(cls, fields: ExtractedFields) -> "UIPlan":
        return cls(
            goal     = fields.goal,
            layout   = fields.layout,
            entities = fields.entities or [],
            actions  = fields.actions  or [],
            feedback = fields.feedback or [],
            style    = fields.style,
        )
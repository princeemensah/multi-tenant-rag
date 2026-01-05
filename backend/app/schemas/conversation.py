"""Schemas for conversation sessions and messages."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class ConversationSessionCreate(BaseModel):
    """Payload to create a new conversation session."""

    title: str | None = Field(default=None, min_length=1, max_length=255)


class ConversationSessionRename(BaseModel):
    """Payload to rename an existing session."""

    title: str = Field(..., min_length=1, max_length=255)


class ConversationSessionResponse(BaseModel):
    """Serialized conversation session."""

    id: UUID
    tenant_id: UUID
    created_by_id: UUID | None = None
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationSessionList(BaseModel):
    """Paginated sessions collection."""

    sessions: list[ConversationSessionResponse]
    total: int
    page: int
    size: int
    pages: int


class ConversationMessageCreate(BaseModel):
    """Payload to append a message to a session."""

    role: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    metadata: dict[str, object] | None = None


class ConversationMessageResponse(BaseModel):
    """Serialized conversation message."""

    id: UUID
    conversation_id: UUID
    tenant_id: UUID
    author_id: UUID | None = None
    role: str
    content: str
    metadata: dict[str, object] = Field(
        default_factory=dict,
        validation_alias="message_metadata",
        serialization_alias="metadata",
    )
    sequence: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationMessageList(BaseModel):
    """Window of conversation messages."""

    session_id: UUID
    messages: list[ConversationMessageResponse]
    remaining: int | None = None
    next_before: int | None = None


class ConversationContextResponse(BaseModel):
    """LLM-ready conversation context."""

    session_id: UUID
    messages: list[dict[str, str]]
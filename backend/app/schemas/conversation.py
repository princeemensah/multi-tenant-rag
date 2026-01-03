"""Schemas for conversation sessions and messages."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class ConversationSessionCreate(BaseModel):
    """Payload to create a new conversation session."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)


class ConversationSessionRename(BaseModel):
    """Payload to rename an existing session."""

    title: str = Field(..., min_length=1, max_length=255)


class ConversationSessionResponse(BaseModel):
    """Serialized conversation session."""

    id: UUID
    tenant_id: UUID
    created_by_id: Optional[UUID] = None
    title: str
    message_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationSessionList(BaseModel):
    """Paginated sessions collection."""

    sessions: List[ConversationSessionResponse]
    total: int
    page: int
    size: int
    pages: int


class ConversationMessageCreate(BaseModel):
    """Payload to append a message to a session."""

    role: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    metadata: Optional[Dict[str, object]] = None


class ConversationMessageResponse(BaseModel):
    """Serialized conversation message."""

    id: UUID
    conversation_id: UUID
    tenant_id: UUID
    author_id: Optional[UUID] = None
    role: str
    content: str
    metadata: Dict[str, object] = Field(
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
    messages: List[ConversationMessageResponse]
    remaining: Optional[int] = None
    next_before: Optional[int] = None


class ConversationContextResponse(BaseModel):
    """LLM-ready conversation context."""

    session_id: UUID
    messages: List[Dict[str, str]]

```}
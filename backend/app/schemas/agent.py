"""Pydantic models for agent orchestration endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.intent_service import IntentType


class ContextSnippet(BaseModel):
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    score: float = 0.0
    text: str
    source: Optional[str] = None


class AgentIntent(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    entities: List[str] = Field(default_factory=list)
    requested_action: Optional[str] = None
    raw_response: Optional[str] = None


class AgentToolResult(BaseModel):
    status: str
    detail: str
    data: Dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: AgentToolResult


class AgentResult(BaseModel):
    response: str
    contexts: List[ContextSnippet]
    model_info: Optional[str] = None


class AgentExecution(BaseModel):
    intent: AgentIntent
    result: AgentResult
    action: Optional[AgentAction] = None


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    query: str
    max_chunks: int = Field(default=4, ge=1, le=20)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    session_id: Optional[UUID] = None
    conversation: Optional[List[AgentMessage]] = None


class AgentResponse(BaseModel):
    execution: AgentExecution
```}
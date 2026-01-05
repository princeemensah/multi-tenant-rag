"""Pydantic models for agent orchestration endpoints."""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.intent_service import IntentType


class AgentStrategy(str, Enum):
    """Supported orchestration strategies."""

    DIRECT = "direct"
    INFORMED = "informed"


class ContextSnippet(BaseModel):
    chunk_id: str | None = None
    document_id: str | None = None
    score: float = 0.0
    text: str
    source: str | None = None


class AgentIntent(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    entities: list[str] = Field(default_factory=list)
    requested_action: str | None = None
    raw_response: str | None = None


class AgentToolResult(BaseModel):
    status: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: AgentToolResult


class AgentTrace(BaseModel):
    subquery: str
    contexts: list[ContextSnippet] = Field(default_factory=list)


class AgentResult(BaseModel):
    response: str
    contexts: list[ContextSnippet]
    model_info: str | None = None
    subqueries: list[str] = Field(default_factory=list)
    strategy: AgentStrategy = AgentStrategy.DIRECT
    traces: list[AgentTrace] = Field(default_factory=list)


class AgentExecution(BaseModel):
    intent: AgentIntent
    result: AgentResult
    action: AgentAction | None = None


class AgentGuardrailReport(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    has_warnings: bool = False
    info: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    query: str
    max_chunks: int = Field(default=4, ge=1, le=20)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    llm_provider: str | None = None
    llm_model: str | None = None
    session_id: UUID | None = None
    conversation: list[AgentMessage] | None = None
    strategy: AgentStrategy = AgentStrategy.DIRECT


class AgentResponse(BaseModel):
    execution: AgentExecution
    guardrails: AgentGuardrailReport | None = None

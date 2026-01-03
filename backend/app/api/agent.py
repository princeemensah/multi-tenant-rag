"""Agent orchestration endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.dependencies import (
    AgentServiceDep,
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
)
from app.schemas.agent import AgentRequest, AgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/execute", response_model=AgentResponse)
async def execute_agent(
    payload: AgentRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    agent_service: AgentServiceDep,
) -> AgentResponse:
    execution = await agent_service.execute(
        db=db,
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        query=payload.query,
        llm_provider=payload.llm_provider or current_tenant.llm_provider,
        llm_model=payload.llm_model or current_tenant.llm_model,
        conversation=payload.conversation,
        strategy=payload.strategy,
        max_chunks=payload.max_chunks,
        score_threshold=payload.score_threshold,
    )
    logger.info(
        "Agent execution completed",
        extra={
            "tenant": str(current_tenant.id),
            "user": str(current_user.id),
            "intent": execution.intent.intent.value,
        },
    )
    return AgentResponse(execution=execution)

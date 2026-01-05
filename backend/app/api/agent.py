"""Agent orchestration endpoints."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import (
    AgentServiceDep,
    ConversationServiceDep,
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
)
from app.models.query import Query, QueryResponse
from app.schemas.agent import (
    AgentExecution,
    AgentGuardrailReport,
    AgentMessage,
    AgentRequest,
    AgentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _convert_history(raw_history: list[dict[str, Any]]) -> list[AgentMessage]:
    history: list[AgentMessage] = []
    for entry in raw_history:
        role = str(entry.get("role", "user")).strip() or "user"
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        history.append(AgentMessage(role=role, content=content))
    return history


def _build_guardrail_report(execution: AgentExecution) -> AgentGuardrailReport:
    warnings: list[str] = []
    info: dict[str, Any] = {
        "intent": execution.intent.intent.value,
        "intent_confidence": execution.intent.confidence,
        "strategy": execution.result.strategy.value,
        "subqueries": execution.result.subqueries,
        "context_count": len(execution.result.contexts),
    }

    sources: list[str] = []
    for context in execution.result.contexts:
        if context.source and context.source not in sources:
            sources.append(context.source)
    if sources:
        info["sources"] = sources

    if execution.intent.confidence < 0.4:
        warnings.append("Intent classification confidence is low; confirm the requested action or question.")
    if not execution.result.contexts:
        warnings.append("No supporting documents were retrieved for this answer.")
    if execution.action and execution.action.result.status.lower() != "success":
        warnings.append(
            f"Tool '{execution.action.tool}' returned status '{execution.action.result.status}'."
        )
        info["tool_status"] = execution.action.result.status
        info["tool_detail"] = execution.action.result.detail

    return AgentGuardrailReport(warnings=warnings, has_warnings=bool(warnings), info=info)


def _serialise_contexts(execution: AgentExecution) -> list[dict[str, Any]]:
    serialised: list[dict[str, Any]] = []
    for context in execution.result.contexts:
        serialised.append(
            {
                "chunk_id": context.chunk_id,
                "document_id": context.document_id,
                "score": context.score,
                "text": context.text,
                "source": context.source,
            }
        )
    return serialised


def _render_assistant_message(execution: AgentExecution) -> str:
    content = execution.result.response.strip()
    if content:
        return content

    if execution.action:
        detail = execution.action.result.detail.strip()
        status_text = execution.action.result.status.lower()
        if status_text == "success" and detail:
            return detail
        if status_text != "success":
            return detail or "The tool reported an error during execution."
        if execution.action.result.data:
            # Provide a lightweight summary of the returned data keys
            keys = ", ".join(sorted(execution.action.result.data.keys()))
            return f"Action '{execution.action.tool}' completed. Returned fields: {keys}."

    return "Agent execution completed."


def _prepare_conversation(
    *,
    payload: AgentRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> tuple[UUID, int, list[AgentMessage]]:
    if payload.session_id:
        try:
            session_uuid = UUID(str(payload.session_id))
        except ValueError as exc:  # pragma: no cover - validated via FastAPI
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from exc
        session = conversation_service.get_session(db, current_tenant.id, session_uuid)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
    else:
        session = conversation_service.create_session(
            db,
            current_tenant.id,
            created_by_id=current_user.id,
        )
        session_uuid = session.id

    conversation_turn = session.message_count // 2 + 1

    history_limit = 12
    prior_messages = conversation_service.get_context(db, current_tenant.id, session_uuid, limit=history_limit)
    history = _convert_history(prior_messages)
    if payload.conversation:
        history.extend(payload.conversation)

    conversation_service.add_message(
        db,
        current_tenant.id,
        session_uuid,
        role="user",
        content=payload.query,
        author_id=current_user.id,
        metadata={
            "source": "agent_endpoint",
            "strategy": payload.strategy.value,
            "max_chunks": payload.max_chunks,
            "score_threshold": payload.score_threshold,
            "conversation_turn": conversation_turn,
        },
    )

    return session_uuid, conversation_turn, history


def _persist_agent_artifacts(
    *,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
    current_tenant: CurrentTenantDep,
    current_user: CurrentUserDep,
    session_uuid: UUID,
    payload: AgentRequest,
    execution: AgentExecution,
    guardrails: AgentGuardrailReport,
    provider: str,
    model: str,
    conversation_turn: int,
    elapsed_ms: float,
) -> None:
    assistant_text = _render_assistant_message(execution)
    contexts = execution.result.contexts
    metadata: dict[str, Any] = {
        "source": "agent_endpoint",
        "intent": execution.intent.model_dump(),
        "strategy": execution.result.strategy.value,
        "subqueries": execution.result.subqueries,
        "guardrails": guardrails.model_dump(),
    }
    if contexts:
        metadata["retrieved_chunks"] = [ctx.chunk_id for ctx in contexts if ctx.chunk_id]
        metadata["retrieved_documents"] = [ctx.document_id for ctx in contexts if ctx.document_id]
    if execution.action:
        metadata["tool"] = execution.action.model_dump()

    conversation_service.add_message(
        db,
        current_tenant.id,
        session_uuid,
        role="assistant",
        content=assistant_text,
        author_id=None,
        metadata=metadata,
    )

    try:
        retrieved_documents: list[UUID] = []
        for context in contexts:
            if not context.document_id:
                continue
            try:
                retrieved_documents.append(UUID(str(context.document_id)))
            except (TypeError, ValueError):  # pragma: no cover - defensive fallback
                retrieved_documents.append(uuid4())

        context_text = "\n\n".join([ctx.text for ctx in contexts if ctx.text])
        source_attribution = list({ctx.source for ctx in contexts if ctx.source})

        query_record = Query(
            tenant_id=current_tenant.id,
            user_id=current_user.id,
            query_text=payload.query,
            query_type="agent",
            processing_time_ms=elapsed_ms,
            status="completed",
            retrieved_chunks_count=len(contexts),
            retrieved_documents=retrieved_documents,
            similarity_threshold=payload.score_threshold,
            llm_provider=provider,
            llm_model=model,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost=0.0,
            session_id=str(session_uuid),
            conversation_turn=conversation_turn,
            query_metadata={
                "strategy": execution.result.strategy.value,
                "subqueries": execution.result.subqueries,
                "guardrails": guardrails.model_dump(),
                "intent": execution.intent.model_dump(),
                "action": execution.action.model_dump() if execution.action else None,
            },
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        response_record = QueryResponse(
            query_id=query_record.id,
            response_text=assistant_text,
            response_format="text",
            context_used=context_text,
            context_chunks=[ctx.chunk_id for ctx in contexts if ctx.chunk_id],
            source_attribution=source_attribution,
            contains_citations=bool(source_attribution),
            cache_hit=False,
            is_cached=False,
        )
        db.add(response_record)
        db.commit()
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Failed to persist agent query metadata", extra={"error": str(exc)})
        db.rollback()


@router.post("/execute", response_model=AgentResponse)
async def execute_agent(
    payload: AgentRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    agent_service: AgentServiceDep,
    conversation_service: ConversationServiceDep,
) -> AgentResponse:
    session_uuid, conversation_turn, history = _prepare_conversation(
        payload=payload,
        current_user=current_user,
        current_tenant=current_tenant,
        db=db,
        conversation_service=conversation_service,
    )

    provider = payload.llm_provider or current_tenant.llm_provider
    model = payload.llm_model or current_tenant.llm_model

    start = time.perf_counter()
    execution = await agent_service.execute(
        db=db,
        tenant_id=current_tenant.id,
        user_id=current_user.id,
        query=payload.query,
        llm_provider=provider,
        llm_model=model,
        conversation=history,
        strategy=payload.strategy,
        max_chunks=payload.max_chunks,
        score_threshold=payload.score_threshold,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    guardrails = _build_guardrail_report(execution)
    guardrails.info.setdefault("session_id", str(session_uuid))
    guardrails.info.setdefault("conversation_turn", conversation_turn)

    _persist_agent_artifacts(
        db=db,
        conversation_service=conversation_service,
        current_tenant=current_tenant,
        current_user=current_user,
        session_uuid=session_uuid,
        payload=payload,
        execution=execution,
        guardrails=guardrails,
        provider=provider,
        model=model,
        conversation_turn=conversation_turn,
        elapsed_ms=elapsed_ms,
    )

    logger.info(
        "Agent execution completed",
        extra={
            "tenant": str(current_tenant.id),
            "user": str(current_user.id),
            "intent": execution.intent.intent.value,
            "session": str(session_uuid),
        },
    )

    return AgentResponse(execution=execution, guardrails=guardrails)


@router.post("/stream")
async def stream_agent(
    payload: AgentRequest,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    agent_service: AgentServiceDep,
    conversation_service: ConversationServiceDep,
):
    session_uuid, conversation_turn, history = _prepare_conversation(
        payload=payload,
        current_user=current_user,
        current_tenant=current_tenant,
        db=db,
        conversation_service=conversation_service,
    )

    provider = payload.llm_provider or current_tenant.llm_provider
    model = payload.llm_model or current_tenant.llm_model

    async def iterator() -> AsyncGenerator[str, None]:
        yield _sse_event({
            "type": "status",
            "state": "processing",
            "session_id": str(session_uuid),
            "conversation_turn": conversation_turn,
        })

        start = time.perf_counter()
        try:
            execution = await agent_service.execute(
                db=db,
                tenant_id=current_tenant.id,
                user_id=current_user.id,
                query=payload.query,
                llm_provider=provider,
                llm_model=model,
                conversation=history,
                strategy=payload.strategy,
                max_chunks=payload.max_chunks,
                score_threshold=payload.score_threshold,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            guardrails = _build_guardrail_report(execution)
            guardrails.info.setdefault("session_id", str(session_uuid))
            guardrails.info.setdefault("conversation_turn", conversation_turn)

            contexts_payload = _serialise_contexts(execution)
            if execution.intent:
                yield _sse_event(
                    {
                        "type": "intent",
                        "intent": execution.intent.model_dump(),
                        "session_id": str(session_uuid),
                    }
                )
            if contexts_payload:
                yield _sse_event(
                    {
                        "type": "contexts",
                        "contexts": contexts_payload,
                        "session_id": str(session_uuid),
                    }
                )
            if execution.action:
                yield _sse_event(
                    {
                        "type": "action",
                        "action": execution.action.model_dump(),
                        "session_id": str(session_uuid),
                    }
                )

            answer_text = _render_assistant_message(execution)
            yield _sse_event(
                {
                    "type": "answer",
                    "text": answer_text,
                    "strategy": execution.result.strategy.value,
                    "subqueries": execution.result.subqueries,
                    "model": execution.result.model_info,
                    "guardrails": guardrails.model_dump(),
                    "session_id": str(session_uuid),
                }
            )

            _persist_agent_artifacts(
                db=db,
                conversation_service=conversation_service,
                current_tenant=current_tenant,
                current_user=current_user,
                session_uuid=session_uuid,
                payload=payload,
                execution=execution,
                guardrails=guardrails,
                provider=provider,
                model=model,
                conversation_turn=conversation_turn,
                elapsed_ms=elapsed_ms,
            )

            yield _sse_event({"type": "done", "session_id": str(session_uuid)})
        except HTTPException as exc:
            logger.warning(
                "Agent stream aborted",
                extra={"tenant": str(current_tenant.id), "error": str(exc.detail)},
            )
            yield _sse_event({"type": "error", "message": exc.detail})
        except Exception as exc:  # pragma: no cover - streaming resilience
            logger.exception(
                "Agent stream failed",
                extra={"tenant": str(current_tenant.id), "error": str(exc)},
            )
            yield _sse_event({"type": "error", "message": "Agent execution failed."})

    return StreamingResponse(
        iterator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

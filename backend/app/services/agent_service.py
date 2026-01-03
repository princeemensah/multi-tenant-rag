"""Agent orchestration service inspired by WebRAgent flow."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.task import TaskPriority, TaskStatus
from app.schemas.agent import AgentAction, AgentExecution, AgentIntent, AgentResult, AgentToolResult, ContextSnippet
from app.services.embedding_service import EmbeddingService
from app.services.intent_service import IntentClassifier, IntentResult, IntentType
from app.services.llm_service import LLMService
from app.services.prompt_template_service import PromptTemplateService
from app.services.task_service import IncidentService, TaskService
from app.services.vector_service import QdrantVectorService

logger = logging.getLogger(__name__)


class AgentService:
    """Coordinates intent analysis, retrieval, reasoning, and tool execution."""

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        vector_service: Optional[QdrantVectorService] = None,
        task_service: Optional[TaskService] = None,
        incident_service: Optional[IncidentService] = None,
    ) -> None:
        self.llm_service = llm_service or LLMService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_service = vector_service or QdrantVectorService()
        self.task_service = task_service or TaskService()
        self.incident_service = incident_service or IncidentService()
        self.intent_classifier = IntentClassifier(self.llm_service)

    async def execute(
        self,
        *,
        db: Session,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        max_chunks: int = 4,
        score_threshold: float = 0.35,
    ) -> AgentExecution:
        intent = await self.intent_classifier.classify(
            query,
            provider=llm_provider,
            model=llm_model,
        )

        if intent.intent == IntentType.ACTION:
            action_result = await self._handle_action(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                query=query,
                intent=intent,
                provider=llm_provider,
                model=llm_model,
            )
            return AgentExecution(
                intent=AgentIntent(**intent.model_dump()),
                result=AgentResult(response="", contexts=[]),
                action=action_result,
            )

        if intent.intent == IntentType.CLARIFY:
            clarification = (
                "I need a bit more detail to assist. Could you restate what action or analysis you expect?"
            )
            return AgentExecution(
                intent=AgentIntent(**intent.model_dump()),
                result=AgentResult(response=clarification, contexts=[]),
                action=None,
            )

        retrieval = await self._retrieve_information(
            query=query,
            tenant_id=tenant_id,
            provider=llm_provider,
            model=llm_model,
            max_chunks=max_chunks,
            score_threshold=score_threshold,
        )
        return AgentExecution(
            intent=AgentIntent(**intent.model_dump()),
            result=retrieval,
            action=None,
        )

    async def _retrieve_information(
        self,
        *,
        query: str,
        tenant_id: UUID,
        provider: Optional[str],
        model: Optional[str],
        max_chunks: int,
        score_threshold: float,
    ) -> AgentResult:
        subqueries = await self._generate_subqueries(query, provider, model)
        if not subqueries:
            subqueries = [query]

        all_contexts: List[ContextSnippet] = []
        for subquery in subqueries:
            contexts = await self._search_context(subquery, tenant_id, max_chunks, score_threshold)
            all_contexts.extend(contexts)

        if not all_contexts:
            response = "No relevant documents were retrieved for this query."
            return AgentResult(response=response, contexts=[])

        limit = max_chunks * max(1, len(subqueries))
        trimmed_contexts = sorted(all_contexts, key=lambda item: item.score, reverse=True)[:limit]
        context_docs = [context.model_dump() for context in trimmed_contexts]
        llm_response = await self.llm_service.generate_rag_response(
            query=query,
            context_documents=context_docs,
            provider=provider,
            model=model,
            system_prompt=PromptTemplateService.get_system_message("citation_focus"),
            temperature=0.15,
            max_tokens=650,
            stream=False,
        )

        return AgentResult(response=llm_response.content, contexts=trimmed_contexts, model_info=llm_response.model)

    async def _generate_subqueries(
        self,
        query: str,
        provider: Optional[str],
        model: Optional[str],
    ) -> List[str]:
        prompt = PromptTemplateService.decomposition_prompt(query)
        try:
            response = await self.llm_service.generate_text_response(
                prompt=prompt,
                provider=provider,
                model=model,
                system_prompt="You produce concise bullet lists and nothing else.",
                temperature=0.0,
                max_tokens=256,
            )
        except Exception as exc:
            logger.warning("Failed to generate subqueries", extra={"error": str(exc)})
            return []

        lines = [line.strip("-* ") for line in response.content.splitlines() if line.strip()]
        subqueries = [line for line in lines if line]
        return subqueries[:4]

    async def _search_context(
        self,
        subquery: str,
        tenant_id: UUID,
        max_chunks: int,
        score_threshold: float,
    ) -> List[ContextSnippet]:
        embedding = await self.embedding_service.embed_text(subquery)
        if not isinstance(embedding, list):
            raise RuntimeError("Embedding service returned unexpected format")

        vector: List[float]
        if embedding and isinstance(embedding[0], list):  # type: ignore[index]
            vector = embedding[0]  # type: ignore[assignment]
        else:
            vector = embedding  # type: ignore[assignment]

        search_results = await self.vector_service.search_documents(
            tenant_id=str(tenant_id),
            query_embedding=vector,
            limit=max_chunks,
            score_threshold=score_threshold,
        )

        contexts: List[ContextSnippet] = []
        for item in search_results:
            contexts.append(
                ContextSnippet(
                    chunk_id=str(item.get("chunk_id")),
                    document_id=str(item.get("document_id")),
                    score=float(item.get("score", 0.0)),
                    text=str(item.get("text", "")),
                    source=str(item.get("source", "")),
                )
            )
        return contexts

    async def _handle_action(
        self,
        *,
        db: Session,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        intent: IntentResult,
        provider: Optional[str],
        model: Optional[str],
    ) -> AgentAction:
        plan_prompt = PromptTemplateService.action_planner_prompt(query)
        plan_response = await self.llm_service.generate_text_response(
            prompt=plan_prompt,
            provider=provider,
            model=model,
            system_prompt="Map user intent to the provided tools and return JSON only.",
            temperature=0.0,
            max_tokens=256,
        )

        plan = self._parse_action_plan(plan_response.content)
        return await self._execute_action(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            plan=plan,
        )

    def _parse_action_plan(self, payload: str) -> Dict[str, Any]:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            stripped = payload.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                return json.loads(stripped)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to interpret action plan")

    async def _execute_action(
        self,
        *,
        db: Session,
        tenant_id: UUID,
        user_id: UUID,
        plan: Dict[str, Any],
    ) -> AgentAction:
        tool = str(plan.get("tool", "none")).strip().lower()
        arguments = plan.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        if tool == "create_task":
            result = await self._action_create_task(db, tenant_id, user_id, arguments)
        elif tool == "get_open_tasks":
            result = await self._action_list_open_tasks(db, tenant_id)
        elif tool == "summarize_incidents":
            result = await self._action_summarize_incidents(db, tenant_id, arguments)
        else:
            result = AgentToolResult(status="unsupported", detail="No matching tool for this request", data={})

        return AgentAction(tool=tool, arguments=arguments, result=result)

    async def _action_create_task(
        self,
        db: Session,
        tenant_id: UUID,
        user_id: UUID,
        args: Dict[str, Any],
    ) -> AgentToolResult:
        title = str(args.get("title") or "").strip()
        if not title:
            return AgentToolResult(status="failed", detail="Task title missing", data={})

        description = str(args.get("description") or "").strip() or None
        priority_raw = str(args.get("priority") or "medium").strip().lower()
        priority = TaskPriority.MEDIUM
        for option in TaskPriority:
            if option.value.lower() == priority_raw:
                priority = option
                break

        due_date_raw = args.get("due_date")
        due_date = None
        if isinstance(due_date_raw, str) and due_date_raw:
            try:
                due_date = datetime.fromisoformat(due_date_raw)
            except ValueError:
                pass

        task = self.task_service.create_task(
            db=db,
            tenant_id=tenant_id,
            creator_id=user_id,
            title=title,
            description=description,
            priority=priority,
            tags=args.get("tags") if isinstance(args.get("tags"), list) else None,
            metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None,
            due_date=due_date,
            assigned_to_id=None,
        )
        return AgentToolResult(
            status="success",
            detail="Task created",
            data={
                "task_id": str(task.id),
                "title": task.title,
                "priority": task.priority,
                "status": task.status,
            },
        )

    async def _action_list_open_tasks(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> AgentToolResult:
        tasks, _ = self.task_service.list_tasks(db, tenant_id, status_filter=TaskStatus.OPEN)
        items = [
            {
                "task_id": str(task.id),
                "title": task.title,
                "priority": task.priority,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            }
            for task in tasks[:10]
        ]
        return AgentToolResult(status="success", detail=f"Found {len(items)} open tasks", data={"tasks": items})

    async def _action_summarize_incidents(
        self,
        db: Session,
        tenant_id: UUID,
        args: Dict[str, Any],
    ) -> AgentToolResult:
        timeframe = args.get("timeframe_days")
        days = int(timeframe) if isinstance(timeframe, int) else 7
        summary = self.incident_service.summarize_incidents(db, tenant_id, timeframe_days=days)
        recent = [
            {
                "incident_id": str(item.id),
                "title": item.title,
                "severity": item.severity,
                "status": item.status,
            }
            for item in summary.get("recent_incidents", [])
        ]
        payload = dict(summary)
        payload["recent_incidents"] = recent
        return AgentToolResult(status="success", detail="Incident summary generated", data=payload)
*** End Patch
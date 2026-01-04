"""Conversation session and message endpoints."""
from __future__ import annotations

from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies import (
    ConversationServiceDep,
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
)
from app.schemas.conversation import (
    ConversationContextResponse,
    ConversationMessageCreate,
    ConversationMessageList,
    ConversationMessageResponse,
    ConversationSessionCreate,
    ConversationSessionList,
    ConversationSessionRename,
    ConversationSessionResponse,
)

import structlog


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("/", response_model=ConversationSessionList)
def list_conversation_sessions(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
    skip: int = 0,
    limit: int = 20,
) -> ConversationSessionList:
    sessions, total = conversation_service.list_sessions(db, current_tenant.id, limit=limit, skip=skip)
    logger.info(
        "List conversation sessions",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        skip=skip,
        limit=limit,
        total=total,
    )
    size = max(limit, 1)
    page = max(skip // size + 1, 1)
    pages = ceil(total / size) if total else 1
    return ConversationSessionList(sessions=sessions, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=ConversationSessionResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_session(
    payload: ConversationSessionCreate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> ConversationSessionResponse:
    session = conversation_service.create_session(
        db,
        current_tenant.id,
        created_by_id=current_user.id,
        title=payload.title,
    )
    logger.info(
        "Conversation session created",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session.id),
    )
    return session


@router.get("/{session_id}", response_model=ConversationSessionResponse)
def get_conversation_session(
    session_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> ConversationSessionResponse:
    session = conversation_service.get_session(db, current_tenant.id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
    logger.info(
        "Get conversation session",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
    )
    return session


@router.patch("/{session_id}", response_model=ConversationSessionResponse)
def rename_conversation_session(
    session_id: UUID,
    payload: ConversationSessionRename,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> ConversationSessionResponse:
    session = conversation_service.rename_session(
        db,
        current_tenant.id,
        session_id,
        title=payload.title,
    )
    logger.info(
        "Conversation session renamed",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
    )
    return session


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
def delete_conversation_session(
    session_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> None:
    conversation_service.delete_session(db, current_tenant.id, session_id)
    logger.info(
        "Conversation session deleted",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
    )
    return {"message": "Conversation session deleted"}


@router.get("/{session_id}/messages", response_model=ConversationMessageList)
def list_conversation_messages(
    session_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
    limit: int = 50,
    before_sequence: Optional[int] = None,
) -> ConversationMessageList:
    session = conversation_service.get_session(db, current_tenant.id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")

    messages = conversation_service.list_messages(
        db,
        current_tenant.id,
        session_id,
        limit=limit,
        before_sequence=before_sequence,
    )

    remaining = 0
    next_before = None
    if messages:
        earliest_sequence = messages[0].sequence
        remaining = max(earliest_sequence - 1, 0)
        next_before = earliest_sequence

    logger.info(
        "Conversation messages listed",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
        limit=limit,
        remaining=remaining,
    )
    return ConversationMessageList(
        session_id=session_id,
        messages=messages,
        remaining=remaining,
        next_before=next_before,
    )


@router.post("/{session_id}/messages", response_model=ConversationMessageResponse, status_code=status.HTTP_201_CREATED)
def create_conversation_message(
    session_id: UUID,
    payload: ConversationMessageCreate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> ConversationMessageResponse:
    author_id = current_user.id if payload.role == "user" else None
    message = conversation_service.add_message(
        db,
        current_tenant.id,
        session_id,
        role=payload.role,
        content=payload.content,
        author_id=author_id,
        metadata=payload.metadata or {},
    )
    logger.info(
        "Conversation message created",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
        role=payload.role,
    )
    return message


@router.get("/{session_id}/context", response_model=ConversationContextResponse)
def get_conversation_context(
    session_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
    limit: int = 10,
) -> ConversationContextResponse:
    session = conversation_service.get_session(db, current_tenant.id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")

    # Obtain context as list of role/content pairs for downstream LLM use.
    context_messages = conversation_service.get_context(db, current_tenant.id, session_id, limit=limit)
    logger.info(
        "Conversation context retrieved",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
        limit=limit,
        messages=len(context_messages),
    )
    return ConversationContextResponse(session_id=session_id, messages=context_messages)


@router.post("/{session_id}/title/generate")
async def generate_conversation_title(
    session_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    conversation_service: ConversationServiceDep,
) -> dict:
    title = await conversation_service.generate_title(db, current_tenant.id, session_id)
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to generate title")
    logger.info(
        "Conversation title generated",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        session_id=str(session_id),
    )
    return {"title": title}
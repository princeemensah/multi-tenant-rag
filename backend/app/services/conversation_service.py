"""Conversation persistence and retrieval utilities."""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.conversation import ConversationMessage, ConversationSession
from app.services.llm_service import LLMService
from app.services.prompt_template_service import PromptTemplateService

logger = logging.getLogger(__name__)


class ConversationService:
    """Manage conversation sessions and messages for tenants."""

    def __init__(self, llm_service: Optional[LLMService] = None) -> None:
        self.llm_service = llm_service or LLMService()

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------
    def list_sessions(
        self,
        db: Session,
        tenant_id: UUID,
        *,
        limit: int = 20,
        skip: int = 0,
    ) -> Tuple[List[ConversationSession], int]:
        total = (
            db.query(func.count(ConversationSession.id))
            .filter(ConversationSession.tenant_id == tenant_id)
            .scalar()
            or 0
        )
        query = (
            db.query(ConversationSession)
            .filter(ConversationSession.tenant_id == tenant_id)
            .order_by(ConversationSession.updated_at.desc())
        )
        sessions = query.offset(max(skip, 0)).limit(max(limit, 1)).all()
        return sessions, total

    def get_session(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
    ) -> Optional[ConversationSession]:
        return (
            db.query(ConversationSession)
            .filter(
                and_(
                    ConversationSession.id == session_id,
                    ConversationSession.tenant_id == tenant_id,
                )
            )
            .first()
        )

    def create_session(
        self,
        db: Session,
        tenant_id: UUID,
        *,
        created_by_id: Optional[UUID],
        title: Optional[str] = None,
    ) -> ConversationSession:
        session = ConversationSession(
            tenant_id=tenant_id,
            created_by_id=created_by_id,
            title=title or "New conversation",
            message_count=0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info("Conversation session created", extra={"session_id": str(session.id), "tenant": str(tenant_id)})
        return session

    def rename_session(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
        *,
        title: str,
    ) -> ConversationSession:
        session = self._require_session(db, tenant_id, session_id)
        session.title = title
        db.commit()
        db.refresh(session)
        return session

    def delete_session(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
    ) -> None:
        session = self._require_session(db, tenant_id, session_id)
        db.delete(session)
        db.commit()
        logger.info("Conversation session deleted", extra={"session_id": str(session_id), "tenant": str(tenant_id)})

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------
    def add_message(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
        *,
        role: str,
        content: str,
        author_id: Optional[UUID],
        metadata: Optional[Dict[str, object]] = None,
    ) -> ConversationMessage:
        session = self._require_session(db, tenant_id, session_id)
        next_sequence = session.message_count + 1
        message = ConversationMessage(
            conversation_id=session.id,
            tenant_id=tenant_id,
            author_id=author_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
            sequence=next_sequence,
        )
        session.message_count = next_sequence
        db.add(message)
        db.commit()
        db.refresh(message)
        db.refresh(session)
        logger.debug(
            "Conversation message stored",
            extra={"session_id": str(session_id), "message_id": str(message.id), "sequence": next_sequence},
        )
        return message

    def list_messages(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
        *,
        limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[ConversationMessage]:
        session = self._require_session(db, tenant_id, session_id)
        query = (
            db.query(ConversationMessage)
            .filter(
                and_(
                    ConversationMessage.conversation_id == session.id,
                    ConversationMessage.tenant_id == tenant_id,
                )
            )
            .order_by(ConversationMessage.sequence.desc())
        )
        if before_sequence is not None:
            query = query.filter(ConversationMessage.sequence < before_sequence)
        messages = list(reversed(query.limit(max(limit, 1)).all()))
        return messages

    def get_context(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
        *,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        messages = self.list_messages(db, tenant_id, session_id, limit=limit)
        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

    # ------------------------------------------------------------------
    # Title helpers
    # ------------------------------------------------------------------
    async def generate_title(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
    ) -> Optional[str]:
        session = self._require_session(db, tenant_id, session_id)
        first_messages = self.list_messages(db, tenant_id, session_id, limit=2)
        user_message = next((msg for msg in first_messages if msg.role == "user"), None)
        if not user_message:
            return None

        prompt = PromptTemplateService.chat_title_prompt(first_messages)
        try:
            response = await self.llm_service.generate_text_response(
                prompt=prompt,
                provider=None,
                model=None,
                system_prompt="Generate a concise chat title.",
                temperature=0.0,
                max_tokens=32,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to generate chat title",
                extra={"session_id": str(session_id), "error": str(exc)},
            )
            return None

        candidate = response.content.strip().strip("'\"")
        if not candidate:
            return None

        session.title = candidate[:255]
        db.commit()
        db.refresh(session)
        return session.title

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _require_session(
        self,
        db: Session,
        tenant_id: UUID,
        session_id: UUID,
    ) -> ConversationSession:
        session = self.get_session(db, tenant_id, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
        return session

"""Unit tests for ConversationService."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from app.models.tenant import Tenant, TenantUser
from app.services.conversation_service import ConversationService


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage: Dict[str, int] = {}
        self.metadata: Dict[str, Any] = {}


class _FakeLLMService:
    def __init__(self, response_text: str = "Generated Title") -> None:
        self.response_text = response_text
        self.calls: list[str] = []

    async def generate_text_response(self, **kwargs: Any) -> _FakeLLMResponse:
        prompt = kwargs.get("prompt", "")
        self.calls.append(prompt)
        await asyncio.sleep(0)
        return _FakeLLMResponse(self.response_text)


@pytest.fixture
def tenant_and_user(db_session):
    tenant = Tenant(name="Test Tenant", subdomain="test-tenant")
    user = TenantUser(
        tenant=tenant,
        email="user@example.com",
        username="tester",
        hashed_password="hashed",
    )
    db_session.add(tenant)
    db_session.add(user)
    db_session.commit()
    return tenant, user


def test_create_session_and_messages(db_session, tenant_and_user):
    tenant, user = tenant_and_user
    service = ConversationService()

    session = service.create_session(db_session, tenant.id, created_by_id=user.id, title="Kickoff")
    assert session.title == "Kickoff"
    assert session.message_count == 0

    message = service.add_message(
        db_session,
        tenant.id,
        session.id,
        role="user",
        content="Hello",
        author_id=user.id,
        metadata={"foo": "bar"},
    )

    assert message.sequence == 1
    assert session.message_count == 1

    fetched = service.list_messages(db_session, tenant.id, session.id)
    assert len(fetched) == 1
    assert fetched[0].content == "Hello"

    context = service.get_context(db_session, tenant.id, session.id)
    assert context == [{"role": "user", "content": "Hello"}]


def test_generate_title_updates_session(db_session, tenant_and_user):
    tenant, user = tenant_and_user
    fake_llm = _FakeLLMService("Budget Review")
    service = ConversationService(llm_service=fake_llm)

    session = service.create_session(db_session, tenant.id, created_by_id=user.id)
    service.add_message(
        db_session,
        tenant.id,
        session.id,
        role="user",
        content="Let us review quarterly budgets",
        author_id=user.id,
    )
    service.add_message(
        db_session,
        tenant.id,
        session.id,
        role="assistant",
        content="Sure, please provide the figures.",
        author_id=None,
    )

    title = asyncio.run(service.generate_title(db_session, tenant.id, session.id))

    assert title == "Budget Review"
    assert fake_llm.calls, "LLM should be invoked for title generation"
    db_session.refresh(session)
    assert session.title == "Budget Review"
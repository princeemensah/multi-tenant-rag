"""Tests covering document search filters and query analytics summaries."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.api.documents import search_documents
from app.api.queries import get_query_analytics
from app.models.query import Query
from app.models.tenant import Tenant, TenantUser
from app.schemas.document import DocumentSearchRequest
from app.services.vector_service import VectorSearchResults


@pytest.fixture
def tenant_and_user(db_session):
    tenant = Tenant(name="Logging Corp", subdomain="logging")
    user = TenantUser(
        tenant=tenant,
        email="observer@example.com",
        username="observer",
        hashed_password="hashed",
    )
    db_session.add(tenant)
    db_session.add(user)
    db_session.commit()
    return tenant, user


class _StubEmbeddingService:
    async def embed_text(self, text: str):
        return [0.1, 0.2, 0.3]


class _StubVectorService:
    def __init__(self):
        self.last_call = {}

    async def search_documents(
        self,
        *,
        tenant_id,
        query_embedding,
        limit,
        score_threshold,
        filter_conditions,
        offset=0,
    ):
        self.last_call = {
            "tenant_id": tenant_id,
            "query_embedding": query_embedding,
            "limit": limit,
            "score_threshold": score_threshold,
            "filter_conditions": filter_conditions,
            "offset": offset,
        }
        return VectorSearchResults(
            items=[
                {
                    "document_id": str(uuid4()),
                    "chunk_id": str(uuid4()),
                    "score": 0.88,
                    "text": "Retained chunk",
                    "source": "incident.txt",
                    "chunk_index": 0,
                    "page_number": 1,
                    "metadata": {
                        "tags": ["ops"],
                        "filename": "incident.txt",
                        "document_type": "playbook",
                        "created_at": "2024-03-11T00:00:00",
                    },
                }
            ],
            next_offset=offset + limit if limit else None,
            has_more=False,
        )


@pytest.mark.anyio
async def test_document_search_includes_filters(db_session, tenant_and_user):
    tenant, user = tenant_and_user
    request = DocumentSearchRequest(
        query="outage",
        limit=5,
        score_threshold=0.4,
        document_ids=[uuid4()],
        tags=["ops"],
    )

    vector_service = _StubVectorService()
    embedding_service = _StubEmbeddingService()

    response = await search_documents(
        search_request=request,
        current_user=user,
        current_tenant=tenant,
        db=db_session,
        vector_service=vector_service,
        embedding_service=embedding_service,
    )

    assert response.total_found == 1
    assert vector_service.last_call["tenant_id"] == str(tenant.id)
    assert vector_service.last_call["filter_conditions"] == {
        "document_id": [str(request.document_ids[0])],
        "tags": ["ops"],
    }
    assert vector_service.last_call["offset"] == 0
    assert response.results[0].doc_metadata["tags"] == ["ops"]
    assert response.offset == 0
    assert response.next_offset == request.limit
    assert response.has_more is False
    assert response.scores == [pytest.approx(0.88)]


@pytest.mark.anyio
async def test_document_search_filters_by_type_and_dates(db_session, tenant_and_user):
    tenant, user = tenant_and_user
    request = DocumentSearchRequest(
        query="analytics",
        document_types=["playbook", "report"],
        created_after=datetime(2024, 3, 10, tzinfo=UTC),
        created_before=datetime(2024, 3, 20, tzinfo=UTC),
    )

    vector_service = _StubVectorService()
    embedding_service = _StubEmbeddingService()

    await search_documents(
        search_request=request,
        current_user=user,
        current_tenant=tenant,
        db=db_session,
        vector_service=vector_service,
        embedding_service=embedding_service,
    )

    filters = vector_service.last_call["filter_conditions"]
    assert filters["document_type"] == ["playbook", "report"]
    assert filters["created_at_ts"]["gte"] <= filters["created_at_ts"]["lte"]
    assert filters["created_at_ts"]["gte"] == pytest.approx(datetime(2024, 3, 10, tzinfo=UTC).timestamp())
    assert filters["created_at_ts"]["lte"] == pytest.approx(datetime(2024, 3, 20, tzinfo=UTC).timestamp())


@pytest.mark.anyio
async def test_query_analytics_summary(db_session, tenant_and_user):
    tenant, user = tenant_and_user
    earlier = datetime.now(UTC) - timedelta(days=2)
    today = datetime.now(UTC)

    historic_query = Query(
        tenant_id=tenant.id,
        user_id=user.id,
        query_text="Old request",
        query_type="rag",
        processing_time_ms=150.0,
        total_tokens=200,
        estimated_cost=0.12,
        created_at=earlier,
        status="completed",
    )
    recent_query = Query(
        tenant_id=tenant.id,
        user_id=user.id,
        query_text="Recent request",
        query_type="analytics",
        processing_time_ms=90.0,
        total_tokens=120,
        estimated_cost=0.08,
        user_rating=4,
        created_at=today,
        status="completed",
    )
    db_session.add_all([historic_query, recent_query])
    db_session.commit()

    analytics = await get_query_analytics(
        current_user=user,
        current_tenant=tenant,
        db=db_session,
        days=3,
    )

    assert analytics.total_queries == 2
    assert analytics.queries_today == 1
    assert analytics.avg_processing_time_ms == pytest.approx((150.0 + 90.0) / 2)
    assert analytics.avg_tokens_per_query == pytest.approx((200 + 120) / 2)
    assert analytics.total_cost == pytest.approx(0.20)
    types = {item["type"]: item["count"] for item in analytics.top_query_types}
    assert types == {"rag": 1, "analytics": 1}
    assert analytics.avg_rating == pytest.approx(4.0)
    assert analytics.period_start <= analytics.period_end
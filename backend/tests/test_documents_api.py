"""Integration tests for document API upload behavior."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile

from app.dependencies import get_current_tenant, get_current_user, get_document_service
from app.models.document import Document
from app.models.tenant import Tenant, TenantUser


class _StubDocumentService:
    def __init__(self) -> None:
        self.upload_kwargs: dict[str, Any] | None = None
        self.process_calls: list[dict[str, str]] = []
        self._document: Document | None = None
        self.reprocess_candidates: list[Document] = []
        self.reprocess_missing: list[UUID] = []
        self.last_reprocess_query: dict[str, Any] | None = None

    @property
    def document(self) -> Document:
        assert self._document is not None
        return self._document

    async def upload_document(
        self,
        db,
        tenant_id: str,
        file: UploadFile,
        metadata: dict[str, Any] | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> Document:
        # Capture the inputs so the test can assert on merge behavior.
        captured_metadata = metadata or {}
        captured_tags = list(tags or [])
        self.upload_kwargs = {
            "tenant_id": tenant_id,
            "filename": file.filename,
            "metadata": captured_metadata,
            "title": title,
            "tags": captured_tags,
        }

        content = await file.read()
        now = datetime.now(UTC)
        document = Document(
            id=uuid4(),
            tenant_id=UUID(tenant_id),
            filename="stored-summary.txt",
            original_filename=file.filename or "summary.txt",
            content_type=file.content_type or "text/plain",
            file_size=len(content),
            file_path="/tmp/stored-summary.txt",
            status="uploaded",
            total_chunks=0,
            processed_chunks=0,
            title=title,
            summary=None,
            language="en",
            word_count=0,
            collection_name=None,
            embedding_model=None,
            doc_metadata=captured_metadata,
            tags=captured_tags,
            uploaded_at=now,
            processed_at=None,
            created_at=now,
        )
        self._document = document
        return document

    async def process_document(self, db, document_id: str, tenant_id: str) -> bool:
        self.process_calls.append({"document_id": document_id, "tenant_id": tenant_id})
        return True

    def select_documents_for_reprocessing(
        self,
        db,
        tenant_id: str,
        *,
        document_ids: list[str] | None = None,
        status_filter: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Document], list[UUID]]:
        self.last_reprocess_query = {
            "tenant_id": tenant_id,
            "document_ids": document_ids,
            "status_filter": status_filter,
            "limit": limit,
        }
        return list(self.reprocess_candidates), list(self.reprocess_missing)


@pytest.mark.usefixtures("client")
def test_upload_document_merges_payload_and_schedules_processing(client, db_session):
    stub_service = _StubDocumentService()
    client.app.dependency_overrides[get_document_service] = lambda: stub_service

    try:
        tenant = Tenant(name="Acme Corp", subdomain="acme")
        db_session.add(tenant)
        db_session.commit()

        user = TenantUser(
            tenant_id=tenant.id,
            email="admin@acme.io",
            username="acme-admin",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: user
        client.app.dependency_overrides[get_current_tenant] = lambda: tenant

        payload = {
            "metadata": json.dumps({"severity": "p0"}),
            "tags": json.dumps(["analytics", "ops"]),
            "upload_payload": json.dumps(
                {
                    "title": "Ops Summary",
                    "tags": ["ops", "p0"],
                    "metadata": {"document_type": "summary"},
                }
            ),
        }

        files = {"file": ("summary.txt", b"incident summary", "text/plain")}

        response = client.post(
            "/api/v1/documents/upload",
            data=payload,
            files=files,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Ops Summary"
        assert body["doc_metadata"] == {"severity": "p0", "document_type": "summary"}
        assert body["tags"] == ["ops", "p0", "analytics"]

        assert stub_service.upload_kwargs is not None
        assert stub_service.upload_kwargs["metadata"] == {"severity": "p0", "document_type": "summary"}
        assert stub_service.upload_kwargs["tags"] == ["ops", "p0", "analytics"]
        assert stub_service.upload_kwargs["title"] == "Ops Summary"

        assert stub_service.process_calls == [
            {"document_id": str(stub_service.document.id), "tenant_id": str(tenant.id)}
        ]
    finally:
        client.app.dependency_overrides.pop(get_document_service, None)
        client.app.dependency_overrides.pop(get_current_user, None)
        client.app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.usefixtures("client")
def test_reprocess_documents_endpoint_schedules_expected_candidates(client, db_session):
    stub_service = _StubDocumentService()
    client.app.dependency_overrides[get_document_service] = lambda: stub_service

    try:
        tenant = Tenant(name="Acme Corp", subdomain="acme")
        db_session.add(tenant)
        db_session.commit()

        user = TenantUser(
            tenant_id=tenant.id,
            email="admin@acme.io",
            username="acme-admin",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: user
        client.app.dependency_overrides[get_current_tenant] = lambda: tenant

        now = datetime.now(UTC)
        processed = Document(
            id=uuid4(),
            tenant_id=tenant.id,
            filename="processed.txt",
            original_filename="processed.txt",
            content_type="text/plain",
            file_size=12,
            file_path="/tmp/processed.txt",
            status="processed",
            total_chunks=2,
            processed_chunks=2,
            title="Processed",
            summary=None,
            language="en",
            word_count=20,
            collection_name=None,
            embedding_model=None,
            doc_metadata={},
            tags=["ops"],
            uploaded_at=now,
            processed_at=now,
            created_at=now,
        )

        uploaded = Document(
            id=uuid4(),
            tenant_id=tenant.id,
            filename="uploaded.txt",
            original_filename="uploaded.txt",
            content_type="text/plain",
            file_size=10,
            file_path="/tmp/uploaded.txt",
            status="uploaded",
            total_chunks=0,
            processed_chunks=0,
            title="Uploaded",
            summary=None,
            language="en",
            word_count=0,
            collection_name=None,
            embedding_model=None,
            doc_metadata={},
            tags=["ops"],
            uploaded_at=now,
            processed_at=None,
            created_at=now,
        )

        missing_id = uuid4()
        stub_service.reprocess_candidates = [processed, uploaded]
        stub_service.reprocess_missing = [missing_id]

        payload = {
            "document_ids": [str(processed.id), str(uploaded.id), str(missing_id)],
        }

        response = client.post(
            "/api/v1/documents/reprocess",
            json=payload,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["requested"] == 3
        assert body["matched"] == 2
        assert body["scheduled"] == 1
        assert body["skipped"] == 1
        assert str(missing_id) in [entry for entry in body["missing"]]

        actions = {item["document_id"]: item["action"] for item in body["results"]}
        assert actions[str(uploaded.id)] == "queued"
        assert actions[str(processed.id)] == "skipped"
        assert actions[str(missing_id)] == "missing"

        assert stub_service.process_calls == [
            {"document_id": str(uploaded.id), "tenant_id": str(tenant.id)}
        ]

        assert stub_service.last_reprocess_query == {
            "tenant_id": str(tenant.id),
            "document_ids": [str(processed.id), str(uploaded.id), str(missing_id)],
            "status_filter": None,
            "limit": None,
        }
    finally:
        client.app.dependency_overrides.pop(get_document_service, None)
        client.app.dependency_overrides.pop(get_current_user, None)
        client.app.dependency_overrides.pop(get_current_tenant, None)
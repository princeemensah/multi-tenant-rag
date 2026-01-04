from __future__ import annotations
import io
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.config import settings
from app.models.document import Document, DocumentChunk
from app.models.tenant import Tenant
from app.services.document_service import DocumentService


def _make_upload(filename: str, content: bytes) -> UploadFile:
    headers = Headers({"content-type": "text/plain"})
    return UploadFile(filename=filename, file=io.BytesIO(content), headers=headers)


class _StubEmbeddingService:
    model_name = "stub"

    def __init__(self) -> None:
        self.last_chunk_args: dict[str, int] | None = None

    def chunk_text_for_embedding(self, text: str, max_chunk_size: int = 512, overlap_size: int = 50):
        self.last_chunk_args = {"max_chunk_size": max_chunk_size, "overlap_size": overlap_size}
        t = text.strip()
        return [{"text": t, "chunk_index": 0, "start_char": 0, "end_char": len(t), "chunk_size": len(t)}]

    async def embed_document_chunks(self, chunks):
        return [
            {
                **chunk,
                "embedding": [0.1, 0.2, 0.3],
                "embedding_model": self.model_name,
                "embedding_dimension": 3,
            }
            for chunk in chunks
        ]


class _StubVectorService:
    def __init__(self) -> None:
        self.init_calls = 0
        self.deleted: list[tuple[str, str]] = []
        self.add_calls: list[dict[str, object]] = []
        self.default_collection = "test-documents"

    async def init_collection(self, collection_name=None):
        self.init_calls += 1
        return True

    async def delete_document(self, tenant_id, document_id, collection_name=None):
        self.deleted.append((tenant_id, document_id))
        return True

    async def add_documents(self, *, tenant_id, documents, collection_name=None):
        self.add_calls.append({"tenant_id": tenant_id, "documents": documents})
        return True


@pytest.mark.anyio
async def test_upload_document_stores_metadata(tmp_path, db_session, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = DocumentService()

    tenant = Tenant(name="Docs", subdomain="docs")
    db_session.add(tenant)
    db_session.commit()

    upload = _make_upload("note.txt", b"alpha beta")

    document = await service.upload_document(
        db=db_session,
        tenant_id=str(tenant.id),
        file=upload,
        metadata={"source": "lab"},
        title="Lab Notes",
        tags=["alpha", "beta"],
    )

    assert (tmp_path / document.filename).exists()
    assert (document.title, document.doc_metadata, document.tags, document.status) == (
        "Lab Notes",
        {"source": "lab"},
        ["alpha", "beta"],
        "uploaded",
    )
    assert document.file_size == len(b"alpha beta")


@pytest.mark.anyio
async def test_process_document_creates_chunks(tmp_path, db_session, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "chunk_max_chars", 256)
    monkeypatch.setattr(settings, "chunk_overlap_chars", 32)
    service = DocumentService()
    embedding_stub = _StubEmbeddingService()
    service.embedding_service = embedding_stub
    vector_stub = _StubVectorService()
    service.vector_service = vector_stub

    tenant = Tenant(name="Vec", subdomain="vec")
    db_session.add(tenant)
    db_session.commit()

    upload = _make_upload("summary.txt", b"incident summary")
    metadata = {"document_type": "summary", "created_at": "2024-03-12T10:00:00Z"}

    document = await service.upload_document(
        db=db_session,
        tenant_id=str(tenant.id),
        file=upload,
        metadata=metadata,
        tags=["analytics"],
    )

    success = await service.process_document(db=db_session, document_id=str(document.id), tenant_id=str(tenant.id))
    assert success is True

    db_session.refresh(document)
    assert (document.status, document.total_chunks, document.embedding_model) == ("processed", 1, "stub")
    assert document.processed_at is not None

    chunk = db_session.query(DocumentChunk).filter_by(document_id=document.id).one()
    assert chunk.doc_metadata == metadata

    expected_ts = datetime(2024, 3, 12, 10, 0, tzinfo=UTC).timestamp()
    assert vector_stub.deleted == [(str(tenant.id), str(document.id))]
    payload = vector_stub.add_calls[0]["documents"][0]
    assert (payload["tags"], payload["document_type"], payload["created_at"]) == (
        ["analytics"],
        "summary",
        "2024-03-12T10:00:00+00:00",
    )
    assert payload["created_at_ts"] == pytest.approx(expected_ts)
    assert payload["metadata"]["document_metadata"] == metadata
    assert embedding_stub.last_chunk_args == {"max_chunk_size": 256, "overlap_size": 32}


@pytest.mark.anyio
async def test_process_document_handles_empty_text(tmp_path, db_session, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = DocumentService()
    service.embedding_service = _StubEmbeddingService()
    vector_stub = _StubVectorService()
    service.vector_service = vector_stub

    tenant = Tenant(name="Empty", subdomain="empty")
    db_session.add(tenant)
    db_session.commit()

    upload = _make_upload("blank.txt", b"")

    document = await service.upload_document(
        db=db_session,
        tenant_id=str(tenant.id),
        file=upload,
    )

    success = await service.process_document(db=db_session, document_id=str(document.id), tenant_id=str(tenant.id))
    assert success is False

    db_session.refresh(document)
    assert (document.status, document.total_chunks) == ("failed", 0)
    assert db_session.query(DocumentChunk).filter_by(document_id=document.id).count() == 0
    assert vector_stub.add_calls == []


def test_select_documents_for_reprocessing_orders_and_reports_missing(tmp_path, db_session, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = DocumentService()

    tenant = Tenant(name="Batch", subdomain="batch")
    db_session.add(tenant)
    db_session.commit()

    other_tenant = Tenant(name="Other", subdomain="other")
    db_session.add(other_tenant)
    db_session.commit()

    now = datetime.now(UTC)
    doc_uploaded = Document(
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

    doc_processed = Document(
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

    doc_other = Document(
        tenant_id=other_tenant.id,
        filename="other.txt",
        original_filename="other.txt",
        content_type="text/plain",
        file_size=8,
        file_path="/tmp/other.txt",
        status="uploaded",
        total_chunks=0,
        processed_chunks=0,
        title="Other",
        summary=None,
        language="en",
        word_count=0,
        collection_name=None,
        embedding_model=None,
        doc_metadata={},
        tags=[],
        uploaded_at=now,
        processed_at=None,
        created_at=now,
    )

    db_session.add_all([doc_uploaded, doc_processed, doc_other])
    db_session.commit()

    missing_uuid = uuid.uuid4()
    documents, missing = service.select_documents_for_reprocessing(
        db=db_session,
        tenant_id=str(tenant.id),
        document_ids=[str(doc_processed.id), str(doc_uploaded.id), str(missing_uuid)],
    )

    assert [doc.id for doc in documents] == [doc_processed.id, doc_uploaded.id]
    assert missing == [missing_uuid]

    filtered_docs, _ = service.select_documents_for_reprocessing(
        db=db_session,
        tenant_id=str(tenant.id),
        status_filter="uploaded",
        limit=1,
    )
    assert len(filtered_docs) == 1
    assert filtered_docs[0].status == "uploaded"

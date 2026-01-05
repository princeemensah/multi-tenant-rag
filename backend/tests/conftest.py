"""Pytest fixtures for backend tests."""
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "JSON"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Ensure configuration picks up test-friendly defaults before app imports.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("DEFAULT_LLM_PROVIDER", "fallback")

from app.database.base import Base  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402

# Import models so metadata is populated for table creation.
from app.models import conversation, document, query, task, tenant  # noqa: F401,E402


def _reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def _prepare_database() -> Iterator[None]:
    _reset_database()
    yield
    _reset_database()


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    from app.services.vector_service import QdrantVectorService

    monkeypatch.setattr(QdrantVectorService, "init_collection", AsyncMock(return_value=True))
    monkeypatch.setattr(QdrantVectorService, "health_check", AsyncMock(return_value=True))

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

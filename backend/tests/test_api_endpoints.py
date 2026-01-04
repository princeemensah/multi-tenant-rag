"""FastAPI endpoint smoke tests covering health, auth, documents, and queries."""
from __future__ import annotations

import uuid

import pytest


class TestHealthEndpoints:
    """Health check and root status tests."""

    def test_health_check(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "healthy"
        assert "version" in payload
        assert "app_name" in payload

    def test_root_endpoint(self, client):
        response = client.get("/")

        assert response.status_code == 200
        payload = response.json()
        assert "message" in payload
        assert "version" in payload


class TestAuthEndpoints:
    """Authentication edge cases."""

    @pytest.fixture()
    def sample_user_data(self):
        return {
            "email": "user@example.com",
            "username": "user",
            "password": "secret123",
            "role": "user",
        }

    def test_register_user_without_tenant(self, client, sample_user_data):
        missing_tenant_id = str(uuid.uuid4())

        response = client.post(
            "/api/v1/auth/register",
            json=sample_user_data,
            params={"tenant_id": missing_tenant_id},
        )

        assert response.status_code == 404

    def test_login_with_invalid_credentials(self, client):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "wrong"},
        )

        assert response.status_code == 401

    def test_access_protected_endpoint_without_auth(self, client):
        response = client.get("/api/v1/auth/me")

        assert response.status_code == 401


class TestDocumentEndpoints:
    """Document access protections."""

    def test_list_documents_requires_auth(self, client):
        response = client.get("/api/v1/documents/")

        assert response.status_code == 401

    def test_upload_document_requires_auth(self, client):
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", "test content", "text/plain")},
        )

        assert response.status_code == 401


class TestQueryEndpoints:
    """Query endpoints enforce authentication."""

    def test_rag_query_requires_auth(self, client):
        response = client.post(
            "/api/v1/queries/rag",
            json={"query": "What is the meaning of life?", "max_chunks": 5},
        )

        assert response.status_code == 401

    def test_query_history_requires_auth(self, client):
        response = client.get("/api/v1/queries/history")

        assert response.status_code == 401

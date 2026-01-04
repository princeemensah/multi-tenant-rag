"""Tests for the authentication service using the real persistence layer."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from passlib.context import CryptContext

from app.models.tenant import Tenant
from app.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def patch_pwd_context(monkeypatch) -> None:
    from app.services import auth_service as auth_module

    test_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    monkeypatch.setattr(auth_module, "pwd_context", test_context)


@pytest.fixture()
def auth_service() -> AuthService:
    return AuthService()


@pytest.fixture()
def tenant(db_session):
    record = Tenant(name="Tenant QA", subdomain="tenant-qa")
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_hash_and_verify_password(auth_service: AuthService) -> None:
    raw_password = "secret-pass-123"

    hashed = auth_service.hash_password(raw_password)

    assert hashed != raw_password
    assert auth_service.verify_password(raw_password, hashed)
    assert not auth_service.verify_password("wrong-pass", hashed)


def test_create_access_token_and_decode(auth_service: AuthService, tenant: Tenant) -> None:
    token = auth_service.create_access_token(
        user_id="1cd9de72-cba7-4467-be6b-7afdcb40b461",
        tenant_id=str(tenant.id),
        email="user@example.com",
        role="user",
        permissions=["read"],
    )

    payload = auth_service.decode_token(token)

    assert payload["user_id"] == "1cd9de72-cba7-4467-be6b-7afdcb40b461"
    assert payload["tenant_id"] == str(tenant.id)
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "user"
    assert payload["permissions"] == ["read"]


def test_decode_token_invalid(auth_service: AuthService) -> None:
    with pytest.raises(HTTPException):
        auth_service.decode_token("invalid.token.payload")


def test_create_user_success(auth_service: AuthService, db_session, tenant: Tenant) -> None:
    user = auth_service.create_user(
        db=db_session,
        tenant_id=tenant.id,
        email="newuser@example.com",
        username="newuser",
        password="password123",
        role="user",
    )

    assert user.email == "newuser@example.com"
    assert user.username == "newuser"
    assert user.role == "user"
    assert str(user.tenant_id) == str(tenant.id)
    assert auth_service.verify_password("password123", user.hashed_password)


def test_create_user_duplicate_email(auth_service: AuthService, db_session, tenant: Tenant) -> None:
    auth_service.create_user(
        db=db_session,
        tenant_id=tenant.id,
        email="dup@example.com",
        username="dup",
        password="password123",
    )

    with pytest.raises(HTTPException) as excinfo:
        auth_service.create_user(
            db=db_session,
            tenant_id=tenant.id,
            email="dup@example.com",
            username="dup2",
            password="password456",
        )

    assert excinfo.value.status_code == 400


def test_authenticate_user_success(auth_service: AuthService, db_session, tenant: Tenant) -> None:
    user = auth_service.create_user(
        db=db_session,
        tenant_id=tenant.id,
        email="auth@example.com",
        username="authuser",
        password="correct-pass",
    )

    authenticated = auth_service.authenticate_user(
        db=db_session,
        email=user.email,
        password="correct-pass",
    )

    assert authenticated is not None
    assert authenticated.id == user.id


def test_authenticate_user_wrong_password(auth_service: AuthService, db_session, tenant: Tenant) -> None:
    auth_service.create_user(
        db=db_session,
        tenant_id=tenant.id,
        email="authfail@example.com",
        username="authfail",
        password="correct-pass",
    )

    result = auth_service.authenticate_user(
        db=db_session,
        email="authfail@example.com",
        password="wrong-pass",
    )

    assert result is None


def test_authenticate_user_not_found(auth_service: AuthService, db_session, tenant: Tenant) -> None:
    result = auth_service.authenticate_user(
        db=db_session,
        email="missing@example.com",
        password="does-not-matter",
    )

    assert result is None

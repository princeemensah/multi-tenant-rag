"""Authentication service for tenant-scoped JWT flows."""
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.tenant import Tenant, TenantUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handle authentication, authorization, and JWT issuance."""

    def __init__(self) -> None:
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_minutes = settings.jwt_expire_minutes

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(
        self,
        user_id: str,
        tenant_id: str,
        email: str,
        role: str,
        permissions: Optional[List[str]] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "email": email,
            "role": role,
            "permissions": permissions or [],
            "exp": datetime.now(UTC) + timedelta(minutes=self.expire_minutes),
            "iat": datetime.now(UTC),
            "iss": settings.app_name,
            "type": "access_token",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {exc}",
            ) from exc

        if payload.get("type") != "access_token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        return payload

    def authenticate_user(
        self,
        db: Session,
        email: str,
        password: str,
        tenant_identifier: Optional[str] = None,
    ) -> Optional[TenantUser]:
        query = db.query(TenantUser).filter(TenantUser.email == email)

        if tenant_identifier:
            query = query.join(Tenant).filter(Tenant.is_active.is_(True))

            tenant_filters = [Tenant.subdomain == tenant_identifier]
            try:
                tenant_filters.append(Tenant.id == UUID(tenant_identifier))
            except (TypeError, ValueError):
                # Provided identifier is not a UUID; ignore the ID comparison.
                pass

            query = query.filter(or_(*tenant_filters))

        user = query.first()
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None

        user.last_login = datetime.now(UTC)
        db.commit()
        return user

    def create_user(
        self,
        db: Session,
        tenant_id: str,
        email: str,
        username: str,
        password: str,
        role: str = "user",
    ) -> TenantUser:
        existing_user = db.query(TenantUser).filter(
            and_(TenantUser.email == email, TenantUser.tenant_id == tenant_id)
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists in this tenant",
            )

        user = TenantUser(
            tenant_id=tenant_id,
            email=email,
            username=username,
            hashed_password=self.hash_password(password),
            role=role,
            is_active=True,
            email_verified=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_user_by_token(self, db: Session, token: str) -> TenantUser:
        payload = self.decode_token(token)
        user_id = payload.get("user_id")
        tenant_id = payload.get("tenant_id")

        if not user_id or not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user = (
            db.query(TenantUser)
            .filter(
                and_(
                    TenantUser.id == user_id,
                    TenantUser.tenant_id == tenant_id,
                    TenantUser.is_active.is_(True),
                )
            )
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user

    def validate_tenant_access(self, db: Session, token: str, required_tenant_id: str) -> bool:
        payload = self.decode_token(token)
        if payload.get("tenant_id") != required_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant",
            )
        return True

    def check_permission(self, token: str, required_permission: str) -> bool:
        payload = self.decode_token(token)
        if payload.get("role") == "admin":
            return True
        permissions = payload.get("permissions", [])
        return required_permission in permissions

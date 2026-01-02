"""Authentication service placeholder."""
from sqlalchemy.orm import Session

from app.models.tenant import TenantUser


class AuthService:
    """Service responsible for authentication workflows."""

    def create_user(self, db: Session, **kwargs) -> TenantUser:
        raise NotImplementedError

    def authenticate_user(self, db: Session, **kwargs) -> TenantUser:
        raise NotImplementedError

    def create_access_token(self, **kwargs) -> str:
        raise NotImplementedError

    def get_user_by_token(self, db: Session, token: str) -> TenantUser:
        raise NotImplementedError

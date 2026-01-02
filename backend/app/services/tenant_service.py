"""Tenant service placeholder."""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantService:
    """Business logic for tenant lifecycle (to be implemented)."""

    def create_tenant(
        self,
        db: Session,
        name: str,
        subdomain: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> Tenant:
        raise NotImplementedError

    def get_tenant_by_id(self, db: Session, tenant_id: str) -> Optional[Tenant]:
        raise NotImplementedError

    def get_tenant_by_identifier(self, db: Session, identifier: str) -> Optional[Tenant]:
        raise NotImplementedError

    def get_tenant_by_subdomain(self, db: Session, subdomain: str) -> Optional[Tenant]:
        raise NotImplementedError

    def list_tenants(self, db: Session, skip: int = 0, limit: int = 100) -> List[Tenant]:
        raise NotImplementedError

    def update_tenant(self, db: Session, tenant_id: str, updates: Dict[str, Any]) -> Tenant:
        raise NotImplementedError

    def deactivate_tenant(self, db: Session, tenant_id: str) -> bool:
        raise NotImplementedError

    def ensure_tenant_isolation(self, db: Session, tenant_id: str, resource_tenant_id: str) -> None:
        raise NotImplementedError

    def get_tenant_stats(self, db: Session, tenant_id: str) -> Dict[str, Any]:
        raise NotImplementedError

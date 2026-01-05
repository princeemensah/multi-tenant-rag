"""Tenant information endpoints."""
import logging

from fastapi import APIRouter, HTTPException, status

from app.dependencies import (
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    TenantServiceDep,
)
from app.schemas import TenantResponse, TenantStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenant", tags=["Tenant Info"])


@router.get("/info", response_model=TenantResponse)
async def get_current_tenant_info(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
) -> TenantResponse:
    return current_tenant


@router.get("/stats", response_model=TenantStats)
async def get_current_tenant_stats(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
) -> TenantStats:
    try:
        return tenant_service.get_tenant_stats(db, str(current_tenant.id))
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error(
            "Failed to get tenant stats",
            exc_info=exc,
            extra={
                "tenant": str(current_tenant.id),
                "user": getattr(current_user, "email", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tenant statistics",
        ) from exc

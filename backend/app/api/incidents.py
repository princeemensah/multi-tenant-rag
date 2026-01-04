"""Incident management endpoints."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter

from app.dependencies import (
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    IncidentServiceDep,
)
from app.models.task import IncidentSeverity, IncidentStatus
from app.schemas.task import (
    IncidentCreate,
    IncidentList,
    IncidentResponse,
    IncidentSummary,
    IncidentUpdate,
)

import structlog


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("/", response_model=IncidentList)
async def list_incidents(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    incident_service: IncidentServiceDep,
    skip: int = 0,
    limit: int = 20,
    severity: Optional[IncidentSeverity] = None,
    status: Optional[IncidentStatus] = None,
):
    items, total = incident_service.list_incidents(
        db=db,
        tenant_id=current_tenant.id,
        skip=skip,
        limit=limit,
        severity_filter=severity,
        status_filter=status,
    )
    logger.info(
        "List incidents",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        skip=skip,
        limit=limit,
        severity=severity.value if severity else None,
        status=status.value if status else None,
        total=total,
    )
    size = max(limit, 1)
    page = max(1, skip // size + 1)
    pages = (total + size - 1) // size if size else 1
    return IncidentList(incidents=items, total=total, page=page, size=size, pages=pages)


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    incident_service: IncidentServiceDep,
):
    record = incident_service.get_incident(db, current_tenant.id, incident_id)
    logger.info(
        "Get incident",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        incident_id=str(incident_id),
    )
    return record


@router.post("/", response_model=IncidentResponse, status_code=201)
async def create_incident(
    payload: IncidentCreate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    incident_service: IncidentServiceDep,
):
    record = incident_service.create_incident(
        db=db,
        tenant_id=current_tenant.id,
        reporter_id=current_user.id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        status_value=payload.status,
        tags=payload.tags,
        impacted_systems=payload.impacted_systems,
        metadata=payload.metadata,
        summary=payload.summary,
    )
    logger.info(
        "Incident created via API",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        incident_id=str(record.id),
    )
    return record


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    incident_service: IncidentServiceDep,
):
    updates = payload.model_dump(exclude_unset=True)
    record = incident_service.update_incident(db, current_tenant.id, incident_id, updates)
    logger.info(
        "Incident updated via API",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        incident_id=str(incident_id),
        fields=list(updates.keys()),
    )
    return record


@router.get("/summary", response_model=IncidentSummary)
async def summarize_incidents(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    incident_service: IncidentServiceDep,
    timeframe_days: int = 7,
):
    summary = incident_service.summarize_incidents(db, current_tenant.id, timeframe_days)
    logger.info(
        "Incident summary",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        timeframe_days=timeframe_days,
        total=summary["total_incidents"],
    )
    return IncidentSummary(
        timeframe_days=summary["timeframe_days"],
        total_incidents=summary["total_incidents"],
        open_incidents=summary["open_incidents"],
        resolved_incidents=summary["resolved_incidents"],
        incidents_by_severity=summary["incidents_by_severity"],
        incidents_by_status=summary["incidents_by_status"],
        recent_incidents=summary["recent_incidents"],
    )

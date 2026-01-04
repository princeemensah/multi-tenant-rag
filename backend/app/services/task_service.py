"""Services for managing tenant tasks and incidents."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.task import Incident, IncidentSeverity, IncidentStatus, Task, TaskPriority, TaskStatus
from app.models.tenant import TenantUser

import structlog


logger = structlog.get_logger(__name__)


class TaskService:
    """Encapsulates task CRUD logic with tenant isolation."""

    def list_tasks(
        self,
        db: Session,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[TaskStatus] = None,
        priority_filter: Optional[TaskPriority] = None,
    ) -> Tuple[List[Task], int]:
        query = db.query(Task).filter(Task.tenant_id == tenant_id)

        if status_filter:
            query = query.filter(Task.status == status_filter.value)
        if priority_filter:
            query = query.filter(Task.priority == priority_filter.value)

        total = query.count()
        items = (
            query.order_by(Task.created_at.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
            .all()
        )
        return items, total

    def get_task(self, db: Session, tenant_id: UUID, task_id: UUID) -> Task:
        record = (
            db.query(Task)
            .filter(and_(Task.id == task_id, Task.tenant_id == tenant_id))
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return record

    def create_task(
        self,
        db: Session,
        tenant_id: UUID,
        creator_id: Optional[UUID],
        title: str,
        description: Optional[str],
        priority: TaskPriority,
        tags: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
        due_date: Optional[datetime],
        assigned_to_id: Optional[UUID],
    ) -> Task:
        if assigned_to_id:
            assignee = (
                db.query(TenantUser)
                .filter(TenantUser.id == assigned_to_id, TenantUser.tenant_id == tenant_id)
                .first()
            )
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assigned user not found in tenant",
                )

        record = Task(
            tenant_id=tenant_id,
            created_by_id=creator_id,
            assigned_to_id=assigned_to_id,
            title=title,
            description=description,
            priority=priority.value,
            tags=tags or [],
            task_metadata=metadata or {},
            due_date=due_date,
            status=TaskStatus.OPEN.value,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("Task created", task_id=str(record.id), tenant=str(tenant_id))
        return record

    def update_task(
        self,
        db: Session,
        tenant_id: UUID,
        task_id: UUID,
        updates: Dict[str, Any],
    ) -> Task:
        record = self.get_task(db, tenant_id, task_id)

        for field, value in updates.items():
            if field == "assigned_to_id":
                if value is None:
                    record.assigned_to_id = None
                    continue
                assignee = (
                    db.query(TenantUser)
                    .filter(TenantUser.id == value, TenantUser.tenant_id == tenant_id)
                    .first()
                )
                if not assignee:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Assigned user not found in tenant",
                    )
                record.assigned_to_id = value
                continue

            if value is None:
                continue
            if field == "status" and isinstance(value, TaskStatus):
                setattr(record, field, value.value)
                record.completed_at = datetime.now(UTC) if value == TaskStatus.COMPLETED else None
            elif field == "priority" and isinstance(value, TaskPriority):
                setattr(record, field, value.value)
            elif field == "metadata":
                record.task_metadata = value
            elif field == "tags":
                record.tags = value
            elif hasattr(record, field):
                setattr(record, field, value)

        db.commit()
        db.refresh(record)
        logger.info("Task updated", task_id=str(record.id), tenant=str(tenant_id))
        return record


class IncidentService:
    """Tenant-scoped incident management operations."""

    def list_incidents(
        self,
        db: Session,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        severity_filter: Optional[IncidentSeverity] = None,
        status_filter: Optional[IncidentStatus] = None,
    ) -> Tuple[List[Incident], int]:
        query = db.query(Incident).filter(Incident.tenant_id == tenant_id)

        if severity_filter:
            query = query.filter(Incident.severity == severity_filter.value)
        if status_filter:
            query = query.filter(Incident.status == status_filter.value)

        total = query.count()
        items = (
            query.order_by(Incident.detected_at.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
            .all()
        )
        return items, total

    def get_incident(self, db: Session, tenant_id: UUID, incident_id: UUID) -> Incident:
        record = (
            db.query(Incident)
            .filter(and_(Incident.id == incident_id, Incident.tenant_id == tenant_id))
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        return record

    def create_incident(
        self,
        db: Session,
        tenant_id: UUID,
        reporter_id: Optional[UUID],
        title: str,
        description: Optional[str],
        severity: IncidentSeverity,
        status_value: IncidentStatus,
        tags: Optional[List[str]],
        impacted_systems: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
        summary: Optional[str],
    ) -> Incident:
        record = Incident(
            tenant_id=tenant_id,
            reported_by_id=reporter_id,
            title=title,
            description=description,
            severity=severity.value,
            status=status_value.value,
            tags=tags or [],
            impacted_systems=impacted_systems or [],
            incident_metadata=metadata or {},
            summary=summary,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("Incident created", incident_id=str(record.id), tenant=str(tenant_id))
        return record

    def update_incident(
        self,
        db: Session,
        tenant_id: UUID,
        incident_id: UUID,
        updates: Dict[str, Any],
    ) -> Incident:
        record = self.get_incident(db, tenant_id, incident_id)

        for field, value in updates.items():
            if value is None:
                continue
            if field == "severity" and isinstance(value, IncidentSeverity):
                setattr(record, field, value.value)
            elif field == "status" and isinstance(value, IncidentStatus):
                setattr(record, field, value.value)
                if value == IncidentStatus.MITIGATED and not record.mitigated_at:
                    record.mitigated_at = datetime.now(UTC)
                if value == IncidentStatus.RESOLVED and not record.resolved_at:
                    record.resolved_at = datetime.now(UTC)
            elif field == "metadata":
                record.incident_metadata = value
            elif field in {"tags", "impacted_systems"}:
                setattr(record, field, value)
            elif hasattr(record, field):
                setattr(record, field, value)

        acknowledged = updates.get("acknowledged")
        if acknowledged:
            record.acknowledged_at = record.acknowledged_at or datetime.now(UTC)

        mitigated = updates.get("mitigated")
        if mitigated:
            record.mitigated_at = record.mitigated_at or datetime.now(UTC)

        resolved = updates.get("resolved")
        if resolved:
            record.status = IncidentStatus.RESOLVED.value
            record.resolved_at = record.resolved_at or datetime.now(UTC)

        db.commit()
        db.refresh(record)
        logger.info("Incident updated", incident_id=str(record.id), tenant=str(tenant_id))
        return record

    def summarize_incidents(
        self,
        db: Session,
        tenant_id: UUID,
        timeframe_days: int = 7,
    ) -> Dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=max(timeframe_days, 1))

        incidents = (
            db.query(Incident)
            .filter(and_(Incident.tenant_id == tenant_id, Incident.detected_at >= cutoff))
            .order_by(Incident.detected_at.desc())
            .all()
        )

        totals_by_severity: Dict[str, int] = {}
        totals_by_status: Dict[str, int] = {}
        open_count = 0
        resolved_count = 0

        for incident in incidents:
            totals_by_severity[incident.severity] = totals_by_severity.get(incident.severity, 0) + 1
            totals_by_status[incident.status] = totals_by_status.get(incident.status, 0) + 1
            if incident.status != IncidentStatus.RESOLVED.value:
                open_count += 1
            else:
                resolved_count += 1

        return {
            "timeframe_days": timeframe_days,
            "total_incidents": len(incidents),
            "open_incidents": open_count,
            "resolved_incidents": resolved_count,
            "incidents_by_severity": totals_by_severity,
            "incidents_by_status": totals_by_status,
            "recent_incidents": incidents[:10],
        }

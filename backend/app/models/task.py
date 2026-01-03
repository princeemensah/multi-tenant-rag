"""Task and incident ORM models for tenant-scoped operations data."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class TaskStatus(str, Enum):
    """Allowed lifecycle states for tenant tasks."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    """Priority labels used for ranking tenant tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Task(Base):
    """Operational tasks tracked per tenant."""

    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True, index=True)
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default=TaskStatus.OPEN.value, index=True)
    priority = Column(String(16), nullable=False, default=TaskPriority.MEDIUM.value, index=True)
    tags = Column(JSONB, default=list)
    task_metadata = Column(JSONB, default=dict)

    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="tasks")
    created_by = relationship("TenantUser", foreign_keys=[created_by_id], back_populates="created_tasks")
    assigned_to = relationship("TenantUser", foreign_keys=[assigned_to_id], back_populates="assigned_tasks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task id={self.id} tenant={self.tenant_id} status={self.status}>"


class IncidentSeverity(str, Enum):
    """Severity levels for incidents."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Lifecycle states recorded for incidents."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class Incident(Base):
    """Incident records tied to a tenant."""

    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    reported_by_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    severity = Column(String(16), nullable=False, default=IncidentSeverity.MEDIUM.value, index=True)
    status = Column(String(32), nullable=False, default=IncidentStatus.OPEN.value, index=True)

    impacted_systems = Column(JSONB, default=list)
    tags = Column(JSONB, default=list)
    incident_metadata = Column(JSONB, default=dict)

    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    mitigated_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="incidents")
    reported_by = relationship("TenantUser", back_populates="reported_incidents")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Incident id={self.id} tenant={self.tenant_id} severity={self.severity}>"

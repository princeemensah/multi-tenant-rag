"""Schemas for task and incident management."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from app.models.task import IncidentSeverity, IncidentStatus, TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    due_date: datetime | None = None
    assigned_to_id: UUID | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    due_date: datetime | None = None
    assigned_to_id: UUID | None = None


class TaskResponse(TaskBase):
    id: UUID
    tenant_id: UUID
    status: TaskStatus
    created_by_id: UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="task_metadata",
        serialization_alias="metadata",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TaskList(BaseModel):
    tasks: list[TaskResponse]
    total: int
    page: int
    size: int
    pages: int


class IncidentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM)
    status: IncidentStatus = Field(default=IncidentStatus.OPEN)
    tags: list[str] = Field(default_factory=list)
    impacted_systems: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    summary: str | None = Field(default=None, max_length=8000)


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    tags: list[str] | None = None
    impacted_systems: list[str] | None = None
    metadata: dict | None = None
    summary: str | None = Field(default=None, max_length=8000)
    acknowledged: bool | None = None
    mitigated: bool | None = None
    resolved: bool | None = None


class IncidentResponse(IncidentBase):
    id: UUID
    tenant_id: UUID
    reported_by_id: UUID | None = None
    detected_at: datetime
    acknowledged_at: datetime | None = None
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="incident_metadata",
        serialization_alias="metadata",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IncidentList(BaseModel):
    incidents: list[IncidentResponse]
    total: int
    page: int
    size: int
    pages: int


class IncidentSummary(BaseModel):
    timeframe_days: int
    total_incidents: int
    open_incidents: int
    resolved_incidents: int
    incidents_by_severity: dict
    incidents_by_status: dict
    recent_incidents: list[IncidentResponse]
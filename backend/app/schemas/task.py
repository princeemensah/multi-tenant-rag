"""Schemas for task and incident management."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from app.models.task import IncidentSeverity, IncidentStatus, TaskPriority, TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    tags: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    due_date: Optional[datetime] = None
    assigned_to_id: Optional[UUID] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None
    due_date: Optional[datetime] = None
    assigned_to_id: Optional[UUID] = None


class TaskResponse(TaskBase):
    id: UUID
    tenant_id: UUID
    status: TaskStatus
    created_by_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="task_metadata",
        serialization_alias="metadata",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TaskList(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    size: int
    pages: int


class IncidentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=8000)
    severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM)
    status: IncidentStatus = Field(default=IncidentStatus.OPEN)
    tags: List[str] = Field(default_factory=list)
    impacted_systems: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    summary: Optional[str] = Field(default=None, max_length=8000)


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=8000)
    severity: Optional[IncidentSeverity] = None
    status: Optional[IncidentStatus] = None
    tags: Optional[List[str]] = None
    impacted_systems: Optional[List[str]] = None
    metadata: Optional[dict] = None
    summary: Optional[str] = Field(default=None, max_length=8000)
    acknowledged: Optional[bool] = None
    mitigated: Optional[bool] = None
    resolved: Optional[bool] = None


class IncidentResponse(IncidentBase):
    id: UUID
    tenant_id: UUID
    reported_by_id: Optional[UUID] = None
    detected_at: datetime
    acknowledged_at: Optional[datetime] = None
    mitigated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(
        default_factory=dict,
        validation_alias="incident_metadata",
        serialization_alias="metadata",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class IncidentList(BaseModel):
    incidents: List[IncidentResponse]
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
    recent_incidents: List[IncidentResponse]

```}
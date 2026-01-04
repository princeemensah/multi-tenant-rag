"""Task management endpoints for tenant-scoped operations."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.dependencies import (
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    TaskServiceDep,
)
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskList, TaskResponse, TaskUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/", response_model=TaskList)
async def list_tasks(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
    skip: int = 0,
    limit: int = 20,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
):
    items, total = task_service.list_tasks(
        db=db,
        tenant_id=current_tenant.id,
        skip=skip,
        limit=limit,
        status_filter=status,
        priority_filter=priority,
    )
    size = max(limit, 1)
    page = max(1, skip // size + 1)
    pages = (total + size - 1) // size if size else 1
    return TaskList(tasks=items, total=total, page=page, size=size, pages=pages)


@router.get("/open", response_model=TaskList)
async def list_open_tasks(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
    limit: int = 20,
):
    items, total = task_service.list_tasks(
        db=db,
        tenant_id=current_tenant.id,
        skip=0,
        limit=limit,
        status_filter=TaskStatus.OPEN,
    )
    size = max(limit, 1)
    return TaskList(tasks=items, total=total, page=1, size=size, pages=(total + size - 1) // size if size else 1)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    return task_service.get_task(db, current_tenant.id, task_id)


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: TaskCreate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    return task_service.create_task(
        db=db,
        tenant_id=current_tenant.id,
        creator_id=current_user.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        tags=payload.tags,
        metadata=payload.metadata,
        due_date=payload.due_date,
        assigned_to_id=payload.assigned_to_id,
    )


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is None:
        raise HTTPException(status_code=400, detail="Status cannot be null")
    return task_service.update_task(db, current_tenant.id, task_id, updates)


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    updates = {"status": TaskStatus.COMPLETED}
    return task_service.update_task(db, current_tenant.id, task_id, updates)

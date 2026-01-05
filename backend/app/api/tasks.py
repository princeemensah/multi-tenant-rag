"""Task management endpoints for tenant-scoped operations."""
from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException

from app.dependencies import (
    CurrentTenantDep,
    CurrentUserDep,
    DatabaseDep,
    TaskServiceDep,
)
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskList, TaskResponse, TaskUpdate

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/", response_model=TaskList)
async def list_tasks(
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
    skip: int = 0,
    limit: int = 20,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
):
    items, total = task_service.list_tasks(
        db=db,
        tenant_id=current_tenant.id,
        skip=skip,
        limit=limit,
        status_filter=status,
        priority_filter=priority,
    )
    logger.info(
        "List tasks",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        skip=skip,
        limit=limit,
        status=status.value if status else None,
        priority=priority.value if priority else None,
        total=total,
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
    logger.info(
        "List open tasks",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        limit=limit,
        total=total,
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
    record = task_service.get_task(db, current_tenant.id, task_id)
    logger.info(
        "Get task",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        task_id=str(task_id),
    )
    return record


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: TaskCreate,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    record = task_service.create_task(
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
    logger.info(
        "Task created via API",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        task_id=str(record.id),
    )
    return record


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
    record = task_service.update_task(db, current_tenant.id, task_id, updates)
    logger.info(
        "Task updated via API",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        task_id=str(task_id),
        fields=list(updates.keys()),
    )
    return record


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: UUID,
    current_user: CurrentUserDep,
    current_tenant: CurrentTenantDep,
    db: DatabaseDep,
    task_service: TaskServiceDep,
):
    updates = {"status": TaskStatus.COMPLETED}
    record = task_service.update_task(db, current_tenant.id, task_id, updates)
    logger.info(
        "Task completed",
        tenant=str(current_tenant.id),
        user=str(current_user.id),
        task_id=str(task_id),
    )
    return record

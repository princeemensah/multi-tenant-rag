"""API router exports."""
from .agent import router as agent_router
from .auth import router as auth_router
from .documents import router as documents_router
from .incidents import router as incidents_router
from .queries import router as queries_router
from .tasks import router as tasks_router
from .tenants import router as tenants_router

__all__ = [
    "agent_router",
    "auth_router",
    "documents_router",
    "incidents_router",
    "queries_router",
    "tasks_router",
    "tenants_router",
]

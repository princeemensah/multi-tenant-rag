"""FastAPI dependency helpers."""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tenant import Tenant, TenantUser
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.conversation_service import ConversationService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.rerank_service import RerankService
from app.services.retrieval_service import RetrievalService
from app.services.task_service import IncidentService, TaskService
from app.services.tenant_service import TenantService
from app.services.vector_service import QdrantVectorService

security = HTTPBearer(auto_error=False)


@lru_cache
def _cached_auth_service() -> AuthService:
    return AuthService()


def get_auth_service() -> AuthService:
    return _cached_auth_service()


@lru_cache
def _cached_tenant_service() -> TenantService:
    return TenantService()


def get_tenant_service() -> TenantService:
    return _cached_tenant_service()


def get_document_service() -> DocumentService:
    return DocumentService()


def get_vector_service() -> QdrantVectorService:
    return QdrantVectorService()


@lru_cache
def _cached_llm_service() -> LLMService:
    return LLMService()


def get_llm_service() -> LLMService:
    return _cached_llm_service()


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def get_task_service() -> TaskService:
    return TaskService()


def get_incident_service() -> IncidentService:
    return IncidentService()


@lru_cache
def _cached_cache_service() -> CacheService:
    return CacheService()


def get_cache_service() -> CacheService:
    return _cached_cache_service()


@lru_cache
def _cached_rerank_service() -> RerankService:
    return RerankService()


def get_rerank_service() -> RerankService:
    return _cached_rerank_service()


def get_retrieval_service(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_service: QdrantVectorService = Depends(get_vector_service),
    cache_service: CacheService = Depends(get_cache_service),
    rerank_service: RerankService = Depends(get_rerank_service),
) -> RetrievalService:
    return RetrievalService(
        embedding_service=embedding_service,
        vector_service=vector_service,
        cache_service=cache_service,
        rerank_service=rerank_service,
    )


def get_agent_service(
    llm_service: LLMService = Depends(get_llm_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_service: QdrantVectorService = Depends(get_vector_service),
    task_service: TaskService = Depends(get_task_service),
    incident_service: IncidentService = Depends(get_incident_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> AgentService:
    return AgentService(
        llm_service=llm_service,
        embedding_service=embedding_service,
        vector_service=vector_service,
        task_service=task_service,
        incident_service=incident_service,
        retrieval_service=retrieval_service,
    )


def get_conversation_service() -> ConversationService:
    return ConversationService()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> TenantUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return auth_service.get_user_by_token(db, credentials.credentials)


async def get_current_active_user(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


async def get_current_tenant(
    current_user: TenantUser = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> Tenant:
    tenant = tenant_service.get_tenant_by_id(db, str(current_user.tenant_id))
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active or missing",
        )
    return tenant


async def resolve_tenant_from_header(
    x_tenant_id: str | None = Header(None),
    db: Session = Depends(get_db),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> Tenant | None:
    if not x_tenant_id:
        return None

    tenant = tenant_service.get_tenant_by_identifier(db, x_tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or inactive tenant",
        )
    return tenant


async def resolve_tenant_from_subdomain(
    request: Request,
    db: Session = Depends(get_db),
    tenant_service: TenantService = Depends(get_tenant_service),
) -> Tenant | None:
    host = request.headers.get("host", "")
    parts = host.split(".")
    if len(parts) < 3:
        return None

    tenant = tenant_service.get_tenant_by_subdomain(db, parts[0])
    if not tenant or not tenant.is_active:
        return None
    return tenant


def require_admin_role(current_user: TenantUser = Depends(get_current_active_user)) -> TenantUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


def require_user_or_admin_role(
    current_user: TenantUser = Depends(get_current_active_user),
) -> TenantUser:
    if current_user.role not in ("user", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User or admin role required",
        )
    return current_user


async def validate_tenant_access(
    resource_tenant_id: str,
    current_user: TenantUser = Depends(get_current_active_user),
    tenant_service: TenantService = Depends(get_tenant_service),
    db: Session = Depends(get_db),
) -> bool:
    tenant_service.ensure_tenant_isolation(
        db,
        str(current_user.tenant_id),
        resource_tenant_id,
    )
    return True


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
VectorServiceDep = Annotated[QdrantVectorService, Depends(get_vector_service)]
LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]
EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
IncidentServiceDep = Annotated[IncidentService, Depends(get_incident_service)]
CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]
RerankServiceDep = Annotated[RerankService, Depends(get_rerank_service)]
RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]
AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]

CurrentUserDep = Annotated[TenantUser, Depends(get_current_active_user)]
CurrentTenantDep = Annotated[Tenant, Depends(get_current_tenant)]
AdminUserDep = Annotated[TenantUser, Depends(require_admin_role)]
DatabaseDep = Annotated[Session, Depends(get_db)]

"""Authentication and tenant administration routes."""
import logging

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.dependencies import (
    AdminUserDep,
    AuthServiceDep,
    CurrentUserDep,
    DatabaseDep,
    TenantServiceDep,
)
from app.models.tenant import Tenant, TenantUser
from app.schemas import (
    OrganizationSignup,
    OrganizationSignupResponse,
    TenantCreate,
    TenantResponse,
    TenantStats,
    TenantUpdate,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=OrganizationSignupResponse)
async def organization_signup(
    signup_data: OrganizationSignup,
    db: DatabaseDep,
    auth_service: AuthServiceDep,
    tenant_service: TenantServiceDep,
):
    if signup_data.subdomain:
        existing = db.query(Tenant).filter(Tenant.subdomain == signup_data.subdomain).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subdomain already exists",
            )

    existing_user = db.query(TenantUser).filter(TenantUser.email == signup_data.admin_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    tenant = tenant_service.create_tenant(
        db=db,
        name=signup_data.organization_name,
        subdomain=signup_data.subdomain,
        llm_provider=signup_data.llm_provider or "openai",
        llm_model=signup_data.llm_model or "gpt-4o-mini",
    )

    admin_user = auth_service.create_user(
        db=db,
        tenant_id=str(tenant.id),
        email=signup_data.admin_email,
        username=signup_data.admin_username,
        password=signup_data.admin_password,
        role="admin",
    )

    access_token = auth_service.create_access_token(
        user_id=str(admin_user.id),
        tenant_id=str(tenant.id),
        email=admin_user.email,
        role=admin_user.role,
        permissions=["read", "write", "delete", "manage"],
    )

    logger.info("Organization signup completed", extra={"tenant": tenant.name})

    return OrganizationSignupResponse(
        message="Organization created successfully",
        tenant=TenantResponse.model_validate(tenant),
        admin_user=UserResponse.model_validate(admin_user),
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/register", response_model=UserResponse)
async def register_user(
    user_data: UserCreate,
    tenant_id: str,
    db: DatabaseDep,
    auth_service: AuthServiceDep,
    tenant_service: TenantServiceDep,
):
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    user = auth_service.create_user(
        db=db,
        tenant_id=tenant_id,
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        role=user_data.role,
    )

    logger.info("User registered", extra={"tenant_id": tenant_id, "email": user.email})
    return user


@router.post("/login", response_model=TokenResponse)
async def login_user(
    login_data: UserLogin,
    db: DatabaseDep,
    auth_service: AuthServiceDep,
):
    user = auth_service.authenticate_user(
        db=db,
        email=login_data.email,
        password=login_data.password,
        tenant_identifier=login_data.tenant_identifier,
    )

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    permissions: list[str]
    if user.role == "admin":
        permissions = ["read", "write", "delete", "manage"]
    elif user.role == "user":
        permissions = ["read", "write"]
    else:
        permissions = ["read"]

    access_token = auth_service.create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        role=user.role,
        permissions=permissions,
    )

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()

    logger.info(
        "User login successful",
        extra={"tenant_id": str(user.tenant_id), "email": user.email, "role": user.role},
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserResponse.model_validate(user),
        tenant=TenantResponse.model_validate(tenant) if tenant else None,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUserDep) -> UserResponse:
    return current_user


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    tenant_data: TenantCreate,
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
):
    tenant = tenant_service.create_tenant(
        db=db,
        name=tenant_data.name,
        subdomain=tenant_data.subdomain,
        llm_provider=tenant_data.llm_provider or "openai",
        llm_model=tenant_data.llm_model or "gpt-4o-mini",
    )

    logger.info("Tenant created", extra={"tenant_id": tenant.id, "by": admin_user.email})
    return tenant


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
    skip: int = 0,
    limit: int = 100,
):
    return tenant_service.list_tenants(db, skip=skip, limit=limit)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
):
    tenant = tenant_service.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    tenant_update: TenantUpdate,
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
):
    update_data = {k: v for k, v in tenant_update.model_dump().items() if v is not None}
    tenant = tenant_service.update_tenant(db=db, tenant_id=tenant_id, updates=update_data)
    logger.info("Tenant updated", extra={"tenant_id": tenant_id, "by": admin_user.email})
    return tenant


@router.delete("/tenants/{tenant_id}")
async def deactivate_tenant(
    tenant_id: str,
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
):
    success = tenant_service.deactivate_tenant(db, tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    logger.warning("Tenant deactivated", extra={"tenant_id": tenant_id, "by": admin_user.email})
    return {"message": "Tenant deactivated successfully"}


@router.get("/tenants/{tenant_id}/stats", response_model=TenantStats)
async def get_tenant_stats(
    tenant_id: str,
    admin_user: AdminUserDep,
    db: DatabaseDep,
    tenant_service: TenantServiceDep,
):
    return tenant_service.get_tenant_stats(db, tenant_id)


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(
    current_user: CurrentUserDep,
    db: DatabaseDep,
    auth_service: AuthServiceDep,
):
    if current_user.role == "admin":
        permissions = ["read", "write", "delete", "manage"]
    elif current_user.role == "user":
        permissions = ["read", "write"]
    else:
        permissions = ["read"]

    access_token = auth_service.create_access_token(
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id),
        email=current_user.email,
        role=current_user.role,
        permissions=permissions,
    )

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()

    logger.info(
        "Token refreshed",
        extra={"tenant_id": str(current_user.tenant_id), "email": current_user.email},
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserResponse.model_validate(current_user),
        tenant=TenantResponse.model_validate(tenant) if tenant else None,
    )

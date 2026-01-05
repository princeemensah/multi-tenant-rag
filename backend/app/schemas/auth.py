"""Authentication schema placeholders."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: str = "user"


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    tenant_identifier: str | None = None


class UserResponse(UserBase):
    id: UUID | str
    is_active: bool = True
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse | None = None
    tenant: Optional["TenantResponse"] = None


class OrganizationSignup(BaseModel):
    organization_name: str
    admin_email: EmailStr
    admin_username: str
    admin_password: str
    subdomain: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


class TenantCreate(BaseModel):
    name: str
    subdomain: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    subdomain: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    is_active: bool | None = None


class TenantResponse(TenantCreate):
    id: UUID | str
    is_active: bool = True
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class OrganizationSignupResponse(BaseModel):
    message: str
    tenant: TenantResponse
    admin_user: UserResponse
    access_token: str
    token_type: str
    expires_in: int


class TenantStats(BaseModel):
    documents_count: int = 0
    queries_count: int = 0
    users_count: int = 0


TokenResponse.model_rebuild()

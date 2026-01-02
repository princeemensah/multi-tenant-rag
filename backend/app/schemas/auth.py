"""Authentication schema placeholders."""
from datetime import datetime
from typing import List, Optional

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
    tenant_identifier: Optional[str] = None


class UserResponse(UserBase):
    id: str
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: Optional[UserResponse] = None
    tenant: Optional["TenantResponse"] = None


class OrganizationSignup(BaseModel):
    organization_name: str
    admin_email: EmailStr
    admin_username: str
    admin_password: str
    subdomain: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class TenantCreate(BaseModel):
    name: str
    subdomain: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    subdomain: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantCreate):
    id: str
    is_active: bool = True
    created_at: Optional[datetime] = None

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

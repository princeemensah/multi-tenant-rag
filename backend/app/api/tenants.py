"""Tenant endpoints (placeholder)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("/status")
async def tenants_status():
    raise HTTPException(status_code=501, detail="Tenant endpoints not yet implemented")

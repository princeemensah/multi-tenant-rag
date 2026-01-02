"""Authentication endpoints (to be implemented)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/status")
async def auth_status():
    raise HTTPException(status_code=501, detail="Auth endpoints not yet implemented")

"""Document management endpoints (placeholder)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/status")
async def documents_status():
    raise HTTPException(status_code=501, detail="Document endpoints not yet implemented")

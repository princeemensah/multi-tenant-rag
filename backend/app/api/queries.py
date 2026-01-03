"""Query endpoints (placeholder)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.get("/status")
async def queries_status():
    raise HTTPException(status_code=501, detail="Query endpoints not yet implemented")

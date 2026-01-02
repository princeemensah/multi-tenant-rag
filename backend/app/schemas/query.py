"""Query schema placeholders."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    query_text: str
    query_type: str = "search"
    top_k: int = 5
    tenant_id: Optional[str] = None
    filters: Dict[str, Any] = {}


class QueryResponseSchema(BaseModel):
    id: str
    response_text: str
    context_chunks: List[Dict[str, Any]]
    confidence_score: Optional[float] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QueryHistoryEntry(BaseModel):
    id: str
    query_text: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

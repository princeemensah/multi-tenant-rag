"""Document schema placeholders."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DocumentBase(BaseModel):
    filename: str
    content_type: str
    file_size: int


class DocumentCreate(DocumentBase):
    tenant_id: str
    original_filename: str
    metadata: Dict[str, Any] = {}


class DocumentResponse(DocumentBase):
    id: str
    tenant_id: str
    status: str
    total_chunks: int
    processed_chunks: int
    uploaded_at: datetime
    doc_metadata: Dict[str, Any] = {}
    tags: List[str] = []

    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    text_content: str
    vector_id: Optional[str] = None

    class Config:
        from_attributes = True

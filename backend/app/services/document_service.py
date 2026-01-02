"""Document service placeholder."""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentService:
    """Business logic for document ingestion and retrieval."""

    def upload_document(self, db: Session, **kwargs) -> Document:
        raise NotImplementedError

    def get_document(self, db: Session, document_id: str) -> Optional[Document]:
        raise NotImplementedError

    def list_documents(self, db: Session, tenant_id: str, skip: int = 0, limit: int = 100) -> List[Document]:
        raise NotImplementedError

    def update_document_status(self, db: Session, document_id: str, status: str) -> Document:
        raise NotImplementedError

    def delete_document(self, db: Session, document_id: str) -> bool:
        raise NotImplementedError

    def chunk_and_embed(self, db: Session, document: Document) -> Dict[str, Any]:
        raise NotImplementedError

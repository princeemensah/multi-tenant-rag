"""Embedding service placeholder."""
from typing import List


class EmbeddingService:
    """Handles text embedding operations."""

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

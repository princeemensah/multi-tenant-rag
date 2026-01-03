"""Embedding service implementation supporting local and fallback vectors."""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Dict, List, Union

from app.config import settings

try:  # Optional dependency for high-quality embeddings
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover - fallback when library missing
    SentenceTransformer = None

try:  # Optional OpenAI support
    from openai import AsyncOpenAI  # type: ignore
except Exception:  # pragma: no cover - library may not be installed
    AsyncOpenAI = None

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Handles text embedding operations with graceful fallbacks."""

    def __init__(self) -> None:
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self._local_model = self._load_local_model()
        self._openai_client = self._build_openai_client()

    def _load_local_model(self):  # pragma: no cover - costly to load in tests
        if SentenceTransformer is None:
            logger.warning("SentenceTransformer not available; using fallback embeddings")
            return None
        try:
            model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model", extra={"model": self.model_name})
            return model
        except Exception as exc:  # pragma: no cover - robustness only
            logger.error("Failed to load embedding model", extra={"error": str(exc)})
            return None

    def _build_openai_client(self):  # pragma: no cover - optional dependency
        if not settings.openai_api_key or AsyncOpenAI is None:
            return None
        try:
            return AsyncOpenAI(api_key=settings.openai_api_key)
        except Exception as exc:
            logger.error("Failed to initialize OpenAI client", extra={"error": str(exc)})
            return None

    async def embed_text(
        self,
        text: Union[str, List[str]],
        provider: str = "local",
    ) -> Union[List[float], List[List[float]]]:
        single = isinstance(text, str)
        texts = [text] if single else list(text)

        if not texts:
            return [] if single else []

        embeddings: List[List[float]]
        try:
            if provider == "openai" and self._openai_client is not None:
                embeddings = await self._embed_with_openai(texts)
            else:
                embeddings = await self._embed_with_local_model(texts)
        except Exception as exc:
            logger.warning("Embedding provider failed; using fallback", extra={"error": str(exc)})
            embeddings = self._fallback_embeddings(texts)

        return embeddings[0] if single else embeddings

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return await self.embed_text(texts)  # type: ignore[return-value]

    async def _embed_with_local_model(self, texts: List[str]) -> List[List[float]]:
        if not self._local_model:
            return self._fallback_embeddings(texts)

        loop = asyncio.get_running_loop()

        def _encode() -> List[List[float]]:
            vectors = self._local_model.encode(  # type: ignore[union-attr]
                texts,
                convert_to_tensor=False,
                normalize_embeddings=True,
            )
            return vectors.tolist() if hasattr(vectors, "tolist") else list(vectors)

        return await loop.run_in_executor(None, _encode)

    async def _embed_with_openai(self, texts: List[str]) -> List[List[float]]:
        if not self._openai_client:
            raise RuntimeError("OpenAI client not configured")

        response = await self._openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [list(item.embedding) for item in response.data]

    def _fallback_embeddings(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        dim = max(1, self.dimension)

        for text in texts:
            vector = [0.0] * dim
            if text:
                for token in text.split():
                    bucket = hash(token) % dim
                    vector[bucket] += 1.0
            norm = math.sqrt(sum(v * v for v in vector))
            if norm:
                vector = [v / norm for v in vector]
            vectors.append(vector)

        return vectors

    def chunk_text_for_embedding(
        self,
        text: str,
        max_chunk_size: int = 512,
        overlap_size: int = 50,
    ) -> List[Dict[str, Union[int, str]]]:
        if not text:
            return []

        if len(text) <= max_chunk_size:
            return [
                {
                    "text": text.strip(),
                    "chunk_index": 0,
                    "start_char": 0,
                    "end_char": len(text),
                    "chunk_size": len(text.strip()),
                }
            ]

        chunks: List[Dict[str, Union[int, str]]] = []
        start = 0
        chunk_index = 0
        length = len(text)

        while start < length:
            end = min(length, start + max_chunk_size)
            if end < length:
                boundary = text.rfind(" ", start, end)
                if boundary != -1 and boundary > start + overlap_size:
                    end = boundary

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    {
                        "text": chunk_text,
                        "chunk_index": chunk_index,
                        "start_char": start,
                        "end_char": end,
                        "chunk_size": len(chunk_text),
                    }
                )
                chunk_index += 1

            if end >= length:
                break
            start = max(end - overlap_size, start + 1)

        return chunks

    async def embed_document_chunks(
        self,
        chunks: List[Dict[str, Union[int, str]]],
        provider: str = "local",
    ) -> List[Dict[str, Union[int, str, List[float]]]]:
        if not chunks:
            return []

        texts = [str(chunk["text"]) for chunk in chunks]
        embeddings = await self.embed_text(texts, provider)

        enriched: List[Dict[str, Union[int, str, List[float]]]] = []
        for chunk, vector in zip(chunks, embeddings):
            enriched.append(
                {
                    **chunk,
                    "embedding": vector,
                    "embedding_model": self.model_name,
                    "embedding_dimension": len(vector),
                }
            )
        return enriched

    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))
        if not norm1 or not norm2:
            return 0.0
        return dot / (norm1 * norm2)


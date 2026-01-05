"""Evaluate retrieval quality across a set of labelled queries.

Usage:
    python -m app.scripts.evaluate_retrieval --dataset path/to/queries.json

The dataset JSON must contain a top-level "queries" list. Each entry accepts:
    {
        "tenant_id": "<uuid>",
        "query": "...",
        "expected_document_ids": ["<uuid>", ...],      # optional
        "expected_sources": ["filename.pdf", ...],     # optional
        "tags": ["runbook"],                           # optional metadata filters
        "document_ids": ["<uuid>"]                     # optional metadata filter
    }

Hit rate, recall, and mean reciprocal rank (MRR) are computed per tenant.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.services.cache_service import CacheService
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services.retrieval_service import RetrievalService
from app.services.vector_service import QdrantVectorService

logger = logging.getLogger("evaluate_retrieval")


@dataclass
class EvaluationQuery:
    tenant_id: str
    query: str
    expected_document_ids: List[str] = field(default_factory=list)
    expected_sources: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    document_ids: List[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "EvaluationQuery":
        if "tenant_id" not in payload or "query" not in payload:
            raise ValueError("Each query requires tenant_id and query")
        return cls(
            tenant_id=str(payload["tenant_id"]).strip(),
            query=str(payload["query"]).strip(),
            expected_document_ids=[str(item).strip() for item in payload.get("expected_document_ids", [])],
            expected_sources=[str(item).strip() for item in payload.get("expected_sources", [])],
            tags=[str(item).strip() for item in payload.get("tags", [])],
            document_ids=[str(item).strip() for item in payload.get("document_ids", [])],
        )


@dataclass
class QueryEvaluationResult:
    query: EvaluationQuery
    retrieved_ids: List[str]
    retrieved_sources: List[str]
    hit: bool
    reciprocal_rank: float
    matches: int

    def to_summary(self) -> Dict[str, Any]:
        return {
            "query": self.query.query,
            "tenant_id": self.query.tenant_id,
            "hit": self.hit,
            "reciprocal_rank": self.reciprocal_rank,
            "matches": self.matches,
            "retrieved": self.retrieved_ids,
        }


def _normalise(values: Iterable[str]) -> List[str]:
    return [value.lower() for value in values if value]


async def evaluate_query(
    retrieval_service: RetrievalService,
    payload: EvaluationQuery,
    *,
    limit: int,
    score_threshold: float,
    disable_cache: bool,
    disable_reranker: bool,
) -> QueryEvaluationResult:
    filters: Dict[str, Any] = {}
    if payload.tags:
        filters["tags"] = payload.tags
    if payload.document_ids:
        filters["document_id"] = payload.document_ids

    results = await retrieval_service.search_documents(
        tenant_id=payload.tenant_id,
        query=payload.query,
        limit=limit,
        score_threshold=score_threshold,
        filter_conditions=filters or None,
        use_cache=not disable_cache,
        rerank=not disable_reranker,
    )

    retrieved_ids = [str(item.get("document_id", "")) for item in results.items]
    retrieved_sources = [str(item.get("source", "")) for item in results.items]

    expected_ids = set(_normalise(payload.expected_document_ids))
    expected_sources = set(_normalise(payload.expected_sources))

    hit = False
    reciprocal_rank = 0.0
    matches = 0

    for index, (doc_id, source) in enumerate(zip(retrieved_ids, retrieved_sources), start=1):
        normalised_id = doc_id.lower()
        normalised_source = source.lower()
        if expected_ids and normalised_id in expected_ids:
            matches += 1
            if not hit:
                hit = True
                reciprocal_rank = 1.0 / index
        if expected_sources and normalised_source in expected_sources:
            matches += 1
            if not hit:
                hit = True
                reciprocal_rank = 1.0 / index

    # Clamp matches to the number of expectations when both ids and sources overlap
    targets = max(len(expected_ids), len(expected_sources), 1)
    matches = min(matches, targets)

    return QueryEvaluationResult(
        query=payload,
        retrieved_ids=retrieved_ids,
        retrieved_sources=retrieved_sources,
        hit=hit,
        reciprocal_rank=reciprocal_rank,
        matches=matches,
    )


async def run_evaluation(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset).expanduser()
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        return 1

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    queries_raw = payload.get("queries", [])
    if not queries_raw:
        logger.error("Dataset contains no queries")
        return 1

    queries: List[EvaluationQuery] = []
    for entry in queries_raw:
        try:
            query = EvaluationQuery.from_payload(entry)
        except ValueError as exc:
            logger.warning("Skipping invalid query entry: %s", exc)
            continue
        if args.tenant and query.tenant_id != args.tenant:
            continue
        queries.append(query)

    if not queries:
        logger.error("No queries left after filtering; check --tenant filter or dataset")
        return 1

    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    embedding_service = EmbeddingService()
    vector_service = QdrantVectorService()
    cache_service = None if args.disable_cache else CacheService()
    rerank_service = RerankService(enabled=not args.disable_reranker)
    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_service=vector_service,
        cache_service=cache_service,
        rerank_service=rerank_service,
    )

    results: List[QueryEvaluationResult] = []
    for query in queries:
        result = await evaluate_query(
            retrieval_service,
            query,
            limit=args.limit,
            score_threshold=args.score_threshold,
            disable_cache=args.disable_cache,
            disable_reranker=args.disable_reranker,
        )
        results.append(result)
        if args.verbose:
            logger.info("%s", result.to_summary())

    hit_rate = sum(1 for result in results if result.hit) / len(results)
    reciprocal_ranks = [result.reciprocal_rank for result in results if result.reciprocal_rank > 0]
    mrr = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0

    avg_recall = 0.0
    if any(result.query.expected_document_ids or result.query.expected_sources for result in results):
        recalls: List[float] = []
        for result in results:
            targets = max(
                len(result.query.expected_document_ids),
                len(result.query.expected_sources),
                1,
            )
            recalls.append(result.matches / targets)
        avg_recall = statistics.mean(recalls) if recalls else 0.0

    logger.info("Evaluated %d queries", len(results))
    logger.info("Hit rate: %.2f%%", hit_rate * 100)
    logger.info("Mean reciprocal rank: %.4f", mrr)
    if avg_recall:
        logger.info("Average recall: %.2f%%", avg_recall * 100)

    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--dataset", required=True, help="Path to evaluation dataset JSON")
    parser.add_argument("--limit", type=int, default=5, help="Number of chunks to retrieve per query")
    parser.add_argument("--score-threshold", type=float, default=0.35, help="Score threshold for vector search")
    parser.add_argument("--tenant", help="Filter dataset to a specific tenant UUID")
    parser.add_argument("--disable-cache", action="store_true", help="Bypass cache during evaluation")
    parser.add_argument("--disable-reranker", action="store_true", help="Skip reranking step")
    parser.add_argument("--verbose", action="store_true", help="Log per-query summaries")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    try:
        return asyncio.run(run_evaluation(args))
    except KeyboardInterrupt:  # pragma: no cover - interactive cancel
        logger.warning("Evaluation interrupted by user")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

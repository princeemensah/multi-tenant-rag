"""Command-line utilities for document ingestion maintenance.

This script provides administrative helpers to reprocess uploaded documents,
purge tenant data, and regenerate embeddings without requiring manual API
calls. Run with ``python -m app.scripts.manage_documents --help`` for usage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.document import Document
from app.services.document_service import DocumentService
from app.services.tenant_service import TenantService

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "corpus.json"

logger = logging.getLogger("manage_documents")


@dataclass
class SeedDocumentSpec:
    filename: str
    title: str
    content: str
    document_type: str
    tags: List[str]
    created_at: str
    metadata: Dict[str, str]
    content_type: str = "text/plain"


@dataclass
class SeedTenantSpec:
    name: str
    subdomain: str
    llm_provider: Optional[str]
    llm_model: Optional[str]
    documents: List[SeedDocumentSpec]


def _normalize_created_at(value: str) -> str:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = datetime.strptime(candidate, "%Y-%m-%d")
    return parsed.replace(microsecond=0).isoformat()


def load_seed_dataset(path: Path) -> List[SeedTenantSpec]:
    if not path.exists():
        raise FileNotFoundError(f"Seed dataset not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    tenants_payload = payload.get("tenants", [])
    tenants: List[SeedTenantSpec] = []

    for tenant_entry in tenants_payload:
        documents: List[SeedDocumentSpec] = []
        for doc_entry in tenant_entry.get("documents", []):
            created_at = _normalize_created_at(doc_entry.get("created_at", datetime.now(UTC).date().isoformat()))
            metadata = dict(doc_entry.get("metadata", {}))
            metadata.setdefault("document_type", doc_entry.get("document_type"))
            metadata.setdefault("created_at", created_at)
            metadata.setdefault("source_system", "seed_corpus")

            tags = list(dict.fromkeys(doc_entry.get("tags", []) + [doc_entry.get("document_type")]))

            documents.append(
                SeedDocumentSpec(
                    filename=doc_entry.get("filename") or f"{doc_entry['title'].lower().replace(' ', '_')}.txt",
                    title=doc_entry["title"],
                    content=doc_entry["content"],
                    document_type=doc_entry.get("document_type", "reference"),
                    tags=[tag for tag in tags if tag],
                    created_at=created_at,
                    metadata=metadata,
                    content_type=doc_entry.get("content_type", "text/plain"),
                )
            )

        tenants.append(
            SeedTenantSpec(
                name=tenant_entry["name"],
                subdomain=tenant_entry["subdomain"],
                llm_provider=tenant_entry.get("llm_provider"),
                llm_model=tenant_entry.get("llm_model"),
                documents=documents,
            )
        )

    return tenants


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def _with_session(func: Callable[[Session, DocumentService, argparse.Namespace], Awaitable[None]]):
    async def wrapper(args: argparse.Namespace) -> None:
        session = SessionLocal()
        service = DocumentService()
        try:
            await func(session, service, args)
        finally:
            session.close()

    return wrapper


async def _reprocess_document(session: Session, service: DocumentService, document: Document) -> bool:
    logger.info(
        "Reprocessing document %s for tenant %s",
        document.id,
        document.tenant_id,
    )
    try:
        result = await service.process_document(session, str(document.id), str(document.tenant_id))
        status = "completed" if result else "failed"
        logger.info("Reprocess %s: %s", document.id, status)
        return result
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Reprocessing failed for %s: %s", document.id, exc)
        return False


async def _handle_reindex(session: Session, service: DocumentService, args: argparse.Namespace) -> None:
    document_ids_processed = 0
    document_ids_failed = 0

    if args.document_id:
        document = service.get_document(session, args.document_id, args.tenant_id)
        if not document:
            logger.error("Document %s not found", args.document_id)
            return
        if await _reprocess_document(session, service, document):
            document_ids_processed += 1
        else:
            document_ids_failed += 1
    else:
        try:
            tenant_uuid = UUID(args.tenant_id)
        except (TypeError, ValueError):
            logger.error("Valid --tenant-id is required when --document-id is not provided")
            return

        query = session.query(Document).filter(Document.tenant_id == tenant_uuid)
        if args.status:
            query = query.filter(Document.status == args.status)
        if args.limit:
            query = query.limit(args.limit)

        documents: Iterable[Document] = query.all()
        if not documents:
            logger.warning("No documents found for tenant %s", tenant_uuid)
            return

        for document in documents:
            if await _reprocess_document(session, service, document):
                document_ids_processed += 1
            else:
                document_ids_failed += 1

    logger.info(
        "Reindex completed: processed=%d failed=%d",
        document_ids_processed,
        document_ids_failed,
    )


async def _handle_delete(session: Session, service: DocumentService, args: argparse.Namespace) -> None:
    document = service.get_document(session, args.document_id, args.tenant_id)
    if not document:
        logger.error("Document %s not found", args.document_id)
        return

    logger.info("Deleting document %s for tenant %s", document.id, document.tenant_id)
    result = await service.delete_document(session, str(document.id), str(document.tenant_id))
    if result:
        logger.info("Document %s deleted", document.id)
    else:
        logger.error("Failed to delete document %s", document.id)


async def _handle_purge(session: Session, service: DocumentService, args: argparse.Namespace) -> None:
    try:
        tenant_uuid = UUID(args.tenant_id)
    except ValueError:
        logger.error("Invalid --tenant-id provided")
        return

    documents = session.query(Document).filter(Document.tenant_id == tenant_uuid).all()
    if not documents:
        logger.warning("No documents to purge for tenant %s", tenant_uuid)
    else:
        for document in documents:
            await service.delete_document(session, str(document.id), str(document.tenant_id))

    logger.info("Removing residual vector payloads for tenant %s", tenant_uuid)
    await service.vector_service.delete_tenant_data(str(tenant_uuid))
    logger.info("Tenant purge complete for %s", tenant_uuid)


async def _handle_seed(session: Session, service: DocumentService, args: argparse.Namespace) -> None:
    dataset_path = Path(args.dataset).expanduser()
    tenants_specs = load_seed_dataset(dataset_path)
    tenant_filter = {value.lower() for value in args.tenants} if args.tenants else set()

    tenant_service = TenantService()

    total_documents = 0
    total_chunks = 0
    total_duration = 0.0

    logger.info("Seeding corpus from %s", dataset_path)

    for tenant_spec in tenants_specs:
        if tenant_filter and tenant_spec.subdomain.lower() not in tenant_filter:
            continue

        tenant = tenant_service.get_tenant_by_subdomain(session, tenant_spec.subdomain)
        if tenant is None:
            if not args.create_missing_tenants:
                logger.error(
                    "Tenant %s missing; create it first or rerun with --create-missing-tenants",
                    tenant_spec.subdomain,
                )
                continue
            tenant = tenant_service.create_tenant(
                session,
                name=tenant_spec.name,
                subdomain=tenant_spec.subdomain,
                llm_provider=tenant_spec.llm_provider or "openai",
                llm_model=tenant_spec.llm_model or "gpt-4o-mini",
            )
            logger.info("Created tenant %s (%s)", tenant_spec.subdomain, tenant.id)

        for doc_spec in tenant_spec.documents:
            existing = (
                session.query(Document)
                .filter(Document.tenant_id == tenant.id)
                .filter(Document.original_filename == doc_spec.filename)
                .first()
            )

            if existing and not args.force:
                logger.info(
                    "Skipping existing document %s for tenant %s",
                    doc_spec.title,
                    tenant_spec.subdomain,
                )
                continue

            if args.dry_run:
                logger.info(
                    "Dry run: would ingest %s for tenant %s",
                    doc_spec.title,
                    tenant_spec.subdomain,
                )
                continue

            if existing and args.force:
                logger.info(
                    "Replacing existing document %s for tenant %s",
                    doc_spec.title,
                    tenant_spec.subdomain,
                )
                await service.delete_document(session, str(existing.id), str(tenant.id))
                session.flush()

            stored_name = f"seed_{tenant_spec.subdomain}_{doc_spec.filename}"
            file_path = Path(service.upload_dir) / stored_name
            file_bytes = doc_spec.content.encode("utf-8")
            file_path.write_bytes(file_bytes)

            document = Document(
                tenant_id=tenant.id,
                filename=stored_name,
                original_filename=doc_spec.filename,
                content_type=doc_spec.content_type,
                file_size=len(file_bytes),
                file_path=str(file_path),
                status="uploaded",
                title=doc_spec.title,
                tags=doc_spec.tags,
                doc_metadata={**doc_spec.metadata, "seed_subdomain": tenant_spec.subdomain},
            )

            session.add(document)
            session.commit()
            session.refresh(document)

            process_start = perf_counter()
            processed = await service.process_document(session, str(document.id), str(tenant.id))
            duration = perf_counter() - process_start

            if not processed:
                logger.error(
                    "Processing failed for seed document %s in tenant %s",
                    doc_spec.title,
                    tenant_spec.subdomain,
                )
                continue

            session.refresh(document)

            total_documents += 1
            total_chunks += document.processed_chunks or 0
            total_duration += duration

            logger.info(
                "Seeded %s for tenant %s (chunks=%d duration=%.2fs)",
                doc_spec.title,
                tenant_spec.subdomain,
                document.processed_chunks,
                duration,
            )

    if total_documents:
        logger.info(
            "Seed complete: documents=%d chunks=%d avg_duration=%.2fs",
            total_documents,
            total_chunks,
            total_duration / max(total_documents, 1),
        )
    else:
        logger.warning("No documents were seeded")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Document ingestion maintenance utilities")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    reindex = subparsers.add_parser("reindex", help="Reprocess documents and regenerate embeddings")
    reindex.add_argument("--tenant-id", help="Tenant UUID to reprocess")
    reindex.add_argument("--document-id", help="Single document UUID to reprocess")
    reindex.add_argument("--status", help="Optional document status filter, e.g. uploaded")
    reindex.add_argument("--limit", type=int, help="Maximum documents to process for the tenant")
    reindex.set_defaults(handler=_with_session(_handle_reindex))

    delete = subparsers.add_parser("delete", help="Delete a single document and its vectors")
    delete.add_argument("--tenant-id", required=True, help="Tenant UUID owning the document")
    delete.add_argument("--document-id", required=True, help="Document UUID to delete")
    delete.set_defaults(handler=_with_session(_handle_delete))

    purge = subparsers.add_parser("purge", help="Remove all documents and vectors for a tenant")
    purge.add_argument("--tenant-id", required=True, help="Tenant UUID to purge")
    purge.set_defaults(handler=_with_session(_handle_purge))

    seed = subparsers.add_parser("seed", help="Load a multi-tenant document corpus for bootstrapping")
    seed.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to the seed dataset JSON file",
    )
    seed.add_argument(
        "--tenant",
        dest="tenants",
        action="append",
        help="Subdomain of a tenant to seed (can be provided multiple times)",
    )
    seed.add_argument(
        "--create-missing-tenants",
        action="store_true",
        help="Automatically create tenants found in the dataset when absent",
    )
    seed.add_argument(
        "--force",
        action="store_true",
        help="Recreate documents even if they already exist",
    )
    seed.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the seed actions without modifying storage",
    )
    seed.set_defaults(handler=_with_session(_handle_seed))

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    handler: Optional[Callable[[argparse.Namespace], Awaitable[None]]] = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1

    asyncio.run(handler(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())

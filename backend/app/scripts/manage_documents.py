"""Command-line utilities for document ingestion maintenance.

This script provides administrative helpers to reprocess uploaded documents,
purge tenant data, and regenerate embeddings without requiring manual API
calls. Run with ``python -m app.scripts.manage_documents --help`` for usage.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Awaitable, Callable, Iterable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.document import Document
from app.services.document_service import DocumentService

logger = logging.getLogger("manage_documents")


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

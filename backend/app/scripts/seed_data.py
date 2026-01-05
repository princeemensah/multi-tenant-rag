"""Seed the development database with multi-tenant demo data."""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from tempfile import SpooledTemporaryFile
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import SessionLocal
from app.database.connection import create_tables, drop_tables
from app.models.task import Incident, IncidentSeverity, IncidentStatus, Task, TaskPriority
from app.models.tenant import Tenant, TenantUser
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.task_service import IncidentService, TaskService
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)


TENANT_FIXTURES: list[dict[str, Any]] = [
    {
        "name": "Acme Health",
        "subdomain": "acme-health",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "admin": {
            "email": "ops-admin@acmehealth.example",
            "username": "acme-admin",
            "password": "ChangeMe!123",
        },
        "members": [
            {
                "email": "analyst@acmehealth.example",
                "username": "acme-analyst",
                "password": "ChangeMe!123",
                "role": "user",
            }
        ],
        "tasks": [
            {
                "title": "Finalize Zero Trust rollout",
                "description": "Complete final validation of the Zero Trust access policies across the clinical network.",
                "priority": TaskPriority.HIGH,
                "tags": ["zero-trust", "network"],
                "due_in_days": 5,
            },
            {
                "title": "SOC2 evidence collection",
                "description": "Collect access audit logs for Q3 compliance report.",
                "priority": TaskPriority.MEDIUM,
                "tags": ["compliance"],
                "due_in_days": 14,
            },
        ],
        "incidents": [
            {
                "title": "Suspicious EHR access",
                "description": "Multiple failed attempts detected on the cardiology EHR module.",
                "severity": IncidentSeverity.HIGH,
                "status": IncidentStatus.INVESTIGATING,
                "tags": ["ehr", "access"],
                "impacted_systems": ["EHR-Cluster-A"],
            }
        ],
        "documents": [
            {
                "filename": "zero-trust-healthcare.md",
                "title": "Zero Trust Controls for Healthcare",
                "tags": ["zero-trust", "policy"],
                "metadata": {"document_type": "policy", "created_at": "2024-10-01"},
                "content": (
                    "# Zero Trust in Clinical Environments\n\n"
                    "Acme Health is rolling out Zero Trust network access for all clinical workstations."
                    " Every user must authenticate with MFA and device posture must meet baseline requirements."
                ),
            }
        ],
    },
    {
        "name": "Globex Security",
        "subdomain": "globex-security",
        "llm_provider": "anthropic",
        "llm_model": "claude-3-sonnet-20240229",
        "admin": {
            "email": "ops-admin@globex.example",
            "username": "globex-admin",
            "password": "ChangeMe!123",
        },
        "members": [
            {
                "email": "analyst@globex.example",
                "username": "globex-analyst",
                "password": "ChangeMe!123",
                "role": "user",
            }
        ],
        "tasks": [
            {
                "title": "Zero Trust partner onboarding",
                "description": "Coordinate partner access migration to the Zero Trust gateway.",
                "priority": TaskPriority.CRITICAL,
                "tags": ["zero-trust", "onboarding"],
                "due_in_days": 7,
            },
            {
                "title": "Update runbooks",
                "description": "Refresh incident response runbooks with lessons from last quarter.",
                "priority": TaskPriority.MEDIUM,
                "tags": ["runbooks"],
                "due_in_days": 10,
            },
        ],
        "incidents": [
            {
                "title": "Vendor access anomaly",
                "description": "Partner VPN tunnel attempted data exfiltration outside of maintenance window.",
                "severity": IncidentSeverity.CRITICAL,
                "status": IncidentStatus.OPEN,
                "tags": ["vendor", "vpn"],
                "impacted_systems": ["Partner-VPN-Gateway"],
            }
        ],
        "documents": [
            {
                "filename": "globex-zero-trust.md",
                "title": "Zero Trust Partner Guidelines",
                "tags": ["zero-trust", "partners"],
                "metadata": {"document_type": "guideline", "created_at": "2024-09-15"},
                "content": (
                    "# Partner Zero Trust Guidelines\n\n"
                    "Globex enforces device attestation for every external vendor before granting segmentation"
                    " access. Exceptions require CISO approval."
                ),
            }
        ],
    },
    {
        "name": "Innotech Manufacturing",
        "subdomain": "innotech",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "admin": {
            "email": "ops-admin@innotech.example",
            "username": "innotech-admin",
            "password": "ChangeMe!123",
        },
        "members": [
            {
                "email": "analyst@innotech.example",
                "username": "innotech-analyst",
                "password": "ChangeMe!123",
                "role": "user",
            }
        ],
        "tasks": [
            {
                "title": "Factory Zero Trust pilot",
                "description": "Pilot Zero Trust enforcement for robotics controllers in Plant 3.",
                "priority": TaskPriority.HIGH,
                "tags": ["zero-trust", "ot"],
                "due_in_days": 12,
            },
            {
                "title": "Incident drill scheduling",
                "description": "Schedule cross-tenant incident response drill for supply chain disruptions.",
                "priority": TaskPriority.MEDIUM,
                "tags": ["drill", "supply-chain"],
                "due_in_days": 18,
            },
        ],
        "incidents": [
            {
                "title": "PLC firmware anomaly",
                "description": "Unauthorized firmware change detected on robotics cell controller.",
                "severity": IncidentSeverity.HIGH,
                "status": IncidentStatus.MITIGATED,
                "tags": ["plc", "firmware"],
                "impacted_systems": ["Plant3-Robotics-Controller"],
            }
        ],
        "documents": [
            {
                "filename": "innotech-zero-trust.md",
                "title": "Zero Trust for OT Systems",
                "tags": ["zero-trust", "ot"],
                "metadata": {"document_type": "playbook", "created_at": "2024-11-05"},
                "content": (
                    "# OT Zero Trust Playbook\n\n"
                    "Innotech segments programmable logic controllers and applies continuous authentication"
                    " to maintenance engineers leveraging shared principles from Acme and Globex deployments."
                ),
            }
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed multi-tenant demo data.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables before seeding.")
    parser.add_argument("--skip-docs", action="store_true", help="Skip document ingestion stage.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log verbosity.",
    )
    return parser.parse_args()


def ensure_tenant(
    db_session: Session,
    tenant_service: TenantService,
    data: dict[str, Any],
) -> Tenant:
    existing = tenant_service.get_tenant_by_identifier(db_session, data["subdomain"])
    if existing:
        logger.info("Tenant already present", extra={"tenant": existing.subdomain})
        return existing

    tenant = tenant_service.create_tenant(
        db=db_session,
        name=data["name"],
        subdomain=data["subdomain"],
        llm_provider=data["llm_provider"],
        llm_model=data["llm_model"],
    )
    logger.info("Tenant created", extra={"tenant": tenant.subdomain})
    return tenant


def ensure_user(
    db_session: Session,
    auth_service: AuthService,
    tenant_id: UUID,
    email: str,
    username: str,
    password: str,
    role: str,
) -> TenantUser:
    existing = (
        db_session.query(TenantUser)
        .filter(TenantUser.email == email, TenantUser.tenant_id == tenant_id)
        .first()
    )
    if existing:
        return existing
    return auth_service.create_user(
        db=db_session,
        tenant_id=str(tenant_id),
        email=email,
        username=username,
        password=password,
        role=role,
    )


def seed_tasks(
    db_session: Session,
    task_service: TaskService,
    tenant: Tenant,
    creator: TenantUser,
    assignee: TenantUser,
    fixtures: Iterable[dict[str, Any]],
) -> None:
    for task in fixtures:
        existing = (
            db_session.query(Task)
            .filter(Task.tenant_id == tenant.id, Task.title == task["title"])
            .first()
        )
        if existing:
            continue
        due_date = datetime.now(UTC) + timedelta(days=task.get("due_in_days", 7))
        task_service.create_task(
            db=db_session,
            tenant_id=tenant.id,
            creator_id=creator.id,
            title=task["title"],
            description=task.get("description"),
            priority=task.get("priority", TaskPriority.MEDIUM),
            tags=task.get("tags"),
            metadata=task.get("metadata"),
            due_date=due_date,
            assigned_to_id=assignee.id,
        )


def seed_incidents(
    db_session: Session,
    incident_service: IncidentService,
    tenant: Tenant,
    reporter: TenantUser,
    fixtures: Iterable[dict[str, Any]],
) -> None:
    for incident in fixtures:
        existing = (
            db_session.query(Incident)
            .filter(Incident.tenant_id == tenant.id, Incident.title == incident["title"])
            .first()
        )
        if existing:
            continue
        incident_service.create_incident(
            db=db_session,
            tenant_id=tenant.id,
            reporter_id=reporter.id,
            title=incident["title"],
            description=incident.get("description"),
            severity=incident.get("severity", IncidentSeverity.MEDIUM),
            status_value=incident.get("status", IncidentStatus.OPEN),
            tags=incident.get("tags"),
            impacted_systems=incident.get("impacted_systems"),
            metadata=incident.get("metadata"),
            summary=incident.get("summary"),
        )


async def seed_documents(
    db_session: Session,
    tenant: Tenant,
    fixtures: Iterable[dict[str, Any]],
) -> None:
    if not fixtures:
        return

    document_service = DocumentService()
    for item in fixtures:
        buffer = SpooledTemporaryFile(max_size=1024 * 1024)
        buffer.write(item["content"].encode("utf-8"))
        buffer.seek(0)

        upload = UploadFile(
            filename=item["filename"],
            file=buffer,
        )

        try:
            document = await document_service.upload_document(
                db=db_session,
                tenant_id=str(tenant.id),
                file=upload,
                metadata=item.get("metadata"),
                title=item.get("title"),
                tags=item.get("tags"),
            )
            await document_service.process_document(
                db=db_session,
                document_id=str(document.id),
                tenant_id=str(tenant.id),
            )
            logger.info("Seeded document", extra={"tenant": tenant.subdomain, "document_id": str(document.id)})
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to ingest seed document",
                extra={"tenant": tenant.subdomain, "filename": item["filename"], "error": str(exc)},
            )
        finally:
            with suppress(Exception):
                buffer.close()


async def run_seed(reset: bool, skip_docs: bool) -> None:
    if reset:
        drop_tables()
    create_tables()

    db_session = SessionLocal()
    auth_service = AuthService()
    tenant_service = TenantService()
    task_service = TaskService()
    incident_service = IncidentService()

    try:
        for tenant_fixture in TENANT_FIXTURES:
            tenant = ensure_tenant(db_session, tenant_service, tenant_fixture)
            admin_data = tenant_fixture["admin"]
            admin_user = ensure_user(
                db_session,
                auth_service,
                tenant.id,
                admin_data["email"],
                admin_data["username"],
                admin_data["password"],
                role="admin",
            )

            member_fixtures = tenant_fixture.get("members", [])
            if member_fixtures:
                member_data = member_fixtures[0]
                member_user = ensure_user(
                    db_session,
                    auth_service,
                    tenant.id,
                    member_data["email"],
                    member_data["username"],
                    member_data["password"],
                    role=member_data.get("role", "user"),
                )
            else:
                member_user = admin_user

            seed_tasks(
                db_session,
                task_service,
                tenant,
                admin_user,
                member_user,
                tenant_fixture.get("tasks", []),
            )

            seed_incidents(
                db_session,
                incident_service,
                tenant,
                admin_user,
                tenant_fixture.get("incidents", []),
            )

            if not skip_docs:
                await seed_documents(db_session, tenant, tenant_fixture.get("documents", []))

        logger.info("Seeding complete")
    finally:
        db_session.close()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO if not args.quiet else logging.WARNING, format="%(levelname)s %(message)s")
    asyncio.run(run_seed(reset=args.reset, skip_docs=args.skip_docs))


if __name__ == "__main__":
    main()

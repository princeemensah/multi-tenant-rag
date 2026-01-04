"""Database initialization helpers."""
import logging

from sqlalchemy import text

from app.database.base import Base
from app.database.session import engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Verify database connectivity."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        logger.info("Database connection established")


def create_tables() -> None:
    """Create all database tables if they do not exist."""
    from app.models import conversation, document, query, task, tenant  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured")


def drop_tables() -> None:
    """Drop all tables; intended for testing/maintenance only."""
    Base.metadata.drop_all(bind=engine)
    logger.warning("Database tables dropped")

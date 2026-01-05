"""FastAPI application entrypoint for the Multi-Tenant AI Operations Assistant."""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    agent_router,
    auth_router,
    conversations_router,
    documents_router,
    incidents_router,
    queries_router,
    tasks_router,
    tenants_router,
)
from app.config import settings
from app.database import create_tables, init_db
from app.services.vector_service import QdrantVectorService

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown lifecycle events."""
    logger.info("Starting AI Operations Assistant backend")
    try:
        await init_db()
        create_tables()
        logger.info("Database initialized")

        vector_service = QdrantVectorService()
        await vector_service.init_collection()
        logger.info("Vector store initialized")

        if await vector_service.health_check():
            logger.info("Vector store health check passed")
        else:
            logger.warning("Vector store health check failed")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Startup failure", error=str(exc))
        raise

    yield

    logger.info("Shutting down AI Operations Assistant backend")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multi-tenant RAG + agent backend",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_hosts if settings.allowed_hosts != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url),
        method=request.method,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        path=str(request.url),
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error" if not settings.debug else str(exc)},
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "version": settings.app_version,
        "app_name": settings.app_name,
    }


@app.get("/health/detailed")
async def detailed_health() -> dict:
    from app.database.session import engine
    health_status = {"database": "unhealthy", "vector_store": "unhealthy", "llm_services": "unhealthy"}

    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
        health_status["database"] = "healthy"
    except Exception as exc:  # pragma: no cover - diagnostics only
        health_status["database"] = f"unhealthy: {exc}"  # type: ignore[str-bytes-safe]

    try:
        vector_service = QdrantVectorService()
        health_status["vector_store"] = "healthy" if await vector_service.health_check() else "unhealthy"
    except Exception as exc:  # pragma: no cover
        health_status["vector_store"] = f"unhealthy: {exc}"

    try:
        from app.services.llm_service import LLMService

        llm_service = LLMService()
        providers = llm_service.get_available_providers()
        health_status["llm_services"] = (
            f"healthy: {', '.join(providers)}" if providers else "healthy: none configured"
        )
    except Exception as exc:  # pragma: no cover
        health_status["llm_services"] = f"unhealthy: {exc}"

    return {
        "status": "healthy",
        "version": settings.app_version,
        "app_name": settings.app_name,
        "components": health_status,
    }


app.include_router(auth_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")
app.include_router(queries_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs_url": "/docs" if settings.debug else "Docs disabled",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

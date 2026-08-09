import logging.config
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import check_db_connection, create_all_tables
from app.core import (
    activities, auth, admin_stats, hotels, pricing, itineraries, destinations, templates, vehicles, quotations, agents
)
from app.schemas import HealthResponse
from app.services.blob_service import blob_service

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "text": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": settings.LOG_FORMAT,
        },
    },
    "root": {
        "level": settings.LOG_LEVEL,
        "handlers": ["console"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO", "propagate": False, "handlers": ["console"]},
        "sqlalchemy.engine": {"level": "WARNING", "propagate": False, "handlers": ["console"]},
    },
}

if settings.LOG_FILE:
    os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
    LOG_CONFIG["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": settings.LOG_FILE,
        "maxBytes": 10 * 1024 * 1024,  # 10 MB
        "backupCount": 5,
        "formatter": settings.LOG_FORMAT,
    }
    LOG_CONFIG["root"]["handlers"].append("file")

logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.APP_ENV}]")

    # Create DB tables (dev convenience; use Alembic in production)
    if settings.APP_ENV == "development":
        logger.info("Creating database tables (dev mode)")
        await create_all_tables()

    # Ensure Azure containers exist
    if settings.AZURE_STORAGE_ACCOUNT_NAME or settings.AZURE_STORAGE_CONNECTION_STRING:
        try:
            await blob_service.ensure_containers_exist()
            logger.info("Azure Blob containers verified")
        except Exception as exc:
            logger.warning(f"Azure Blob setup skipped: {exc}")

    # Create temp PDF directory
    os.makedirs(settings.PDF_TEMP_DIR, exist_ok=True)

    logger.info("Application startup complete")
    yield

    logger.info("Application shutting down")


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "WanderKashmir B2B Travel Portal API — "
            "Build Kashmir packages, manage hotels, vehicles, itineraries, "
            "generate professional quotations with PDF + email delivery."
        ),
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    from app.core import (
        activities, auth, admin_stats, hotels, pricing,
        itineraries, destinations, templates, vehicles, quotations
    )
    # ── Middleware ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # ── Request logging middleware ─────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} [{duration_ms}ms]",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    # ── Global exception handlers ──────────────────────────────────────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")

        headers = {"Access-Control-Allow-Origin": "*"}

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Internal server error: {str(exc)}"},
            headers=headers
        )

    # ── Health check ───────────────────────────────────────────────────────────
    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health_check():
        db_ok = await check_db_connection()
        azure_ok = False
        if settings.AZURE_STORAGE_ACCOUNT_NAME or settings.AZURE_STORAGE_CONNECTION_STRING:
            try:
                azure_ok = blob_service.check_connection()
            except Exception:
                azure_ok = False

        overall_status = "healthy" if db_ok else "degraded"
        return HealthResponse(
            status=overall_status,
            version=settings.APP_VERSION,
            environment=settings.APP_ENV,
            database=db_ok,
            azure_storage=azure_ok,
        )

    @app.get("/", tags=["System"])
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "docs": "/docs" if settings.DEBUG else "disabled",
            "health": "/health",
        }

    # ── Routers ────────────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(destinations.router, prefix=API_PREFIX)
    app.include_router(itineraries.router, prefix=API_PREFIX)
    app.include_router(hotels.router, prefix=API_PREFIX)
    app.include_router(vehicles.router, prefix=API_PREFIX)
    app.include_router(activities.router, prefix=API_PREFIX)
    app.include_router(quotations.router, prefix=API_PREFIX)
    app.include_router(pricing.router, prefix=API_PREFIX)
    app.include_router(templates.router, prefix=API_PREFIX)
    app.include_router(admin_stats.router, prefix=API_PREFIX)
    app.include_router(agents.router, prefix="/api/v1")

    logger.info(f"Registered {len(app.routes)} routes")
    return app


app = create_app()


# ── Dev runner ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
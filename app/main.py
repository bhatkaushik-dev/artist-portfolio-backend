"""FastAPI application factory, middleware and lifespan."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import dispose_engine, verify_connection
from app.services.storage_service import storage_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Verify the database, open the storage client, then tear both down."""
    logger.info("Starting %s (%s)", settings.PROJECT_NAME, settings.ENVIRONMENT)

    try:
        await verify_connection()
    except Exception:
        # Fail fast in production; locally, let the app boot so /docs is usable
        # while the developer fixes DATABASE_URL.
        logger.exception("Database unreachable at startup")
        if settings.ENVIRONMENT == "production":
            raise

    await storage_service.startup()

    try:
        yield
    finally:
        await storage_service.shutdown()
        await dispose_engine()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        summary="Single source of truth for the artist portfolio site and its JSON-LD.",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    )

    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["ETag", "Last-Modified", "X-Process-Time"],
            max_age=3600,
        )
    else:
        logger.warning("CORS_ORIGINS is empty — browser clients will be blocked")

    # The bootstrap payload is large and highly compressible.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Log rejected payloads — silent 422s are painful to debug from ISR."""
        logger.warning("422 on %s %s: %s", request.method, request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.PROJECT_NAME,
            "bootstrap": f"{settings.API_V1_PREFIX}/bootstrap",
            "health": f"{settings.API_V1_PREFIX}/health",
        }

    return app


app = create_app()

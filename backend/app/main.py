from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import get_redis
from app.db.session import get_engine
from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.campus.router import router as campus_router
from app.modules.claims.router import router as claims_router
from app.modules.desk.router import router as desk_router
from app.modules.items.router import router as items_router
from app.modules.lost_reports.router import router as lost_router
from app.modules.notifications.router import router as notifications_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level, json=s.is_production)
    log.info("api_starting", environment=s.environment, llm=s.llm_provider,
             embeddings=s.embedding_provider)
    yield
    await get_engine().dispose()
    await get_redis().aclose()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Campus Lost & Found API",
        version="0.1.0",
        description="Lost-and-found for a campus: finders report, owners search with an AI "
                    "assistant and get notified later, desks track custody end-to-end.",
        lifespan=lifespan,
        docs_url=None if s.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-requested-with", "x-request-id", "authorization"],
    )
    install_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for r in (auth_router, campus_router, items_router, lost_router, assistant_router,
              claims_router, notifications_router, desk_router):
        api.include_router(r)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Liveness: the process is up. Never touches dependencies."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        """Readiness: dependencies reachable, so the load balancer may route traffic here."""
        checks: dict[str, str] = {}
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as e:
            checks["postgres"] = f"error: {type(e).__name__}"
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {type(e).__name__}"
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks},
                            status_code=200 if ok else 503)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()

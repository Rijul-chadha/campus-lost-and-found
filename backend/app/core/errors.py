"""Map domain + infrastructure errors to RFC 9457 problem+json responses in ONE place."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.core.logging import get_logger, request_id_var
from app.domain.errors import DomainError

log = get_logger(__name__)


def _problem(status: int, code: str, message: str, details: dict[str, object] | None = None,
             headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": f"https://campuslost.dev/errors/{code}", "title": message,
                 "status": status, "code": code, "details": details or {},
                 "request_id": request_id_var.get()},
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        headers = None
        if exc.code == "rate_limited":
            headers = {"Retry-After": str(exc.details.get("retry_after_seconds", 30))}
        return _problem(exc.http_status, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _problem(422, "validation_failed", "Request is invalid", {"errors": errors})

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, __: StaleDataError) -> JSONResponse:
        return _problem(409, "concurrent_update",
                        "This item was changed by someone else. Refresh and try again.")

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        log.info("integrity_error", error=str(exc.orig))
        return _problem(409, "conflict", "That conflicts with existing data.")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return _problem(500, "internal_error", "Something went wrong on our side.")

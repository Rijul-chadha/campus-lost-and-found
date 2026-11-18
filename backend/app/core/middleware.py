from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger, request_id_var
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

log = get_logger("http")
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-requested-with"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id, access log, RED metrics, and a CSRF guard for cookie-authenticated writes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            # Cookies are SameSite=Lax already; requiring a custom header on writes adds
            # defence in depth because browsers cannot send it cross-site without CORS approval.
            if (request.method in _UNSAFE and request.url.path.startswith("/api/")
                    and "authorization" not in request.headers
                    and request.headers.get(CSRF_HEADER) != "campus-lost"):
                return JSONResponse({"code": "csrf", "title": "Missing CSRF header"}, 403)

            response = await call_next(request)
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
            HTTP_LATENCY.labels(request.method, path).observe(elapsed)
            response.headers["x-request-id"] = rid
            if path not in ("/healthz", "/readyz", "/metrics"):
                log.info("request", method=request.method, path=path,
                         status=response.status_code, ms=round(elapsed * 1000, 1))
            return response
        finally:
            request_id_var.reset(token)

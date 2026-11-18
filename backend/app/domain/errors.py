"""Domain error hierarchy. The API layer maps these to HTTP problem responses in one place."""


class DomainError(Exception):
    code = "domain_error"
    http_status = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(DomainError):
    code = "not_found"
    http_status = 404


class PermissionDenied(DomainError):
    code = "permission_denied"
    http_status = 403


class Unauthenticated(DomainError):
    code = "unauthenticated"
    http_status = 401


class Conflict(DomainError):
    code = "conflict"
    http_status = 409


class InvalidTransition(Conflict):
    code = "invalid_transition"


class ValidationFailed(DomainError):
    code = "validation_failed"
    http_status = 422


class RateLimited(DomainError):
    code = "rate_limited"
    http_status = 429

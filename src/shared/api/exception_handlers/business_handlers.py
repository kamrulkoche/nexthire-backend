"""Handlers mapping domain exceptions onto HTTP responses.

Every use case raises a domain exception; this file is the single place that
decides which status code each one becomes. The error envelope is::

    { "status": <code>, "success": false, "error": <message>, "details": {...} }

It deliberately mirrors the success envelope's shape (``status`` + ``success``)
so a client can branch on one field regardless of outcome.
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from ...domain.exceptions import (
    AlreadyExistsError,
    DomainException,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    QuotaExceededError,
    RepositoryError,
    UnauthorizedError,
    ValidationError,
)
from ..exception_registry import register_handler

# A bare getLogger rather than the shared get_logger: handlers are imported very
# early, and this keeps the module free of a config import cycle.
logger = logging.getLogger(__name__)


def _error_response(
    status_code: int, message: str, details: dict | None = None
) -> JSONResponse:
    """Build the standard error envelope.

    Args:
        status_code: HTTP status code
        message: Human-readable error message
        details: Optional structured detail from the domain exception

    Returns:
        JSONResponse carrying the envelope
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status_code,
            "success": False,
            "error": message,
            "details": details or {},
        },
    )


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Map NotFoundError -> 404."""
    logger.info(f"NotFound on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_404_NOT_FOUND, exc.message, exc.details)


async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Map domain ValidationError -> 422.

    422 (not 400) so it matches FastAPI's own validation failures, letting the
    frontend treat all validation the same way.
    """
    logger.info(f"ValidationError on {request.url.path}: {exc.message}")
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message, exc.details
    )


async def unauthorized_handler(
    request: Request, exc: UnauthorizedError
) -> JSONResponse:
    """Map UnauthorizedError -> 401.

    The message is whatever the domain raised, which for a failed login is the
    deliberately vague "Invalid email or password." — never leak which half was
    wrong.
    """
    logger.warning(f"Unauthorized on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_401_UNAUTHORIZED, exc.message, exc.details)


async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    """Map ForbiddenError -> 403."""
    logger.warning(f"Forbidden on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_403_FORBIDDEN, exc.message, exc.details)


async def already_exists_handler(
    request: Request, exc: AlreadyExistsError
) -> JSONResponse:
    """Map AlreadyExistsError -> 409."""
    logger.info(f"AlreadyExists on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_409_CONFLICT, exc.message, exc.details)


async def repository_error_handler(
    request: Request, exc: RepositoryError
) -> JSONResponse:
    """Map RepositoryError -> 500, without leaking the driver message.

    The full text goes to the log; the client gets a generic message, because
    a raw database error can disclose schema details.
    """
    logger.error(f"RepositoryError on {request.url.path}: {exc.message}", exc_info=True)
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "A database error occurred. Please try again.",
    )


async def external_service_handler(
    request: Request, exc: ExternalServiceError
) -> JSONResponse:
    """Map ExternalServiceError -> 502. The upstream failed, not the caller."""
    logger.warning(f"Upstream failure on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_502_BAD_GATEWAY, exc.message, exc.details)


async def quota_exceeded_handler(
    request: Request, exc: QuotaExceededError
) -> JSONResponse:
    """Map QuotaExceededError -> 429, with Retry-After when the reset is known."""
    logger.info(f"Quota exceeded on {request.url.path}: {exc.message}")
    response = _error_response(
        status.HTTP_429_TOO_MANY_REQUESTS, exc.message, exc.details
    )
    if exc.retry_after_seconds:
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response


async def domain_exception_handler(
    request: Request, exc: DomainException
) -> JSONResponse:
    """Catch-all for any DomainException subclass without its own handler -> 400."""
    logger.warning(f"DomainException on {request.url.path}: {exc.message}")
    return _error_response(status.HTTP_400_BAD_REQUEST, exc.message, exc.details)


def register_business_exception_handlers() -> None:
    """Register every domain-exception handler.

    Order matters only in that the catch-all ``DomainException`` is registered
    alongside its subclasses — Starlette resolves the most specific class first.
    """
    register_handler(NotFoundError, not_found_handler)
    register_handler(ValidationError, validation_error_handler)
    register_handler(UnauthorizedError, unauthorized_handler)
    register_handler(ForbiddenError, forbidden_handler)
    register_handler(AlreadyExistsError, already_exists_handler)
    register_handler(RepositoryError, repository_error_handler)
    register_handler(ExternalServiceError, external_service_handler)
    register_handler(QuotaExceededError, quota_exceeded_handler)
    register_handler(DomainException, domain_exception_handler)

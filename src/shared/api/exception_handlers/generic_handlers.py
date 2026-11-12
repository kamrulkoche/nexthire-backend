"""Handlers for non-domain exceptions: FastAPI validation, HTTPException, and
the unhandled catch-all.

CORS note (learned the hard way in sp-company-backend)
-----------------------------------------------------
Starlette binds the bare ``Exception`` handler to ``ServerErrorMiddleware``,
which wraps the app OUTSIDE every user middleware — including CORS. So a
crash-500 never passes back through ``CORSMiddleware`` at any add-order, and a
browser sees an opaque network error instead of the 500. The unhandled handler
therefore attaches the CORS headers itself.
"""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ...utils.config import settings
from ..exception_registry import register_handler

logger = logging.getLogger(__name__)


def _cors_headers(request: Request) -> dict:
    """Build CORS headers for a response that bypasses CORSMiddleware.

    Args:
        request: The incoming request, read for its Origin header

    Returns:
        Header dict, empty when the origin is not allowed
    """
    origin = request.headers.get("origin")
    if not origin:
        return {}
    allowed = settings.cors_origins
    if origin in allowed or "*" in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map FastAPI/Pydantic request-validation failures -> 422.

    Flattens Pydantic's error list into ``{field: message}`` so the frontend can
    render per-field errors without walking the ``loc`` arrays.
    """
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        # loc is like ("body", "email") — drop the source segment.
        location = [str(part) for part in error.get("loc", []) if part != "body"]
        field = ".".join(location) if location else "request"
        # Pydantic prefixes a validator's own ValueError with "Value error, ";
        # the message is for a person, so the framework's label comes off.
        message = str(error.get("msg", "Invalid value"))
        field_errors[field] = message.removeprefix("Value error, ")

    first_message = next(iter(field_errors.values()), "Invalid request")

    logger.info(f"RequestValidationError on {request.url.path}: {field_errors}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "status": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "success": False,
            "error": first_message,
            "details": {"fields": field_errors},
        },
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Re-shape HTTPException into the standard error envelope.

    FastAPI's default body is ``{"detail": ...}``; without this the auth
    dependency's 401s would be the only responses in the API not carrying the
    envelope.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": exc.status_code,
            "success": False,
            "error": exc.detail,
            "details": {},
        },
        headers=getattr(exc, "headers", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all -> 500, with the traceback logged and nothing leaked.

    Carries its own CORS headers; see the module docstring.
    """
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "success": False,
            "error": "An unexpected error occurred.",
            "details": {},
        },
        headers=_cors_headers(request),
    )


def register_generic_exception_handlers() -> None:
    """Register the framework-level and catch-all handlers."""
    register_handler(RequestValidationError, validation_exception_handler)
    register_handler(StarletteHTTPException, http_exception_handler)
    register_handler(Exception, unhandled_exception_handler)

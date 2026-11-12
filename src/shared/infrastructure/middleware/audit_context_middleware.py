"""
Audit context cleanup middleware.

Ensures thread-local audit context is cleared after each request, preventing
user context from leaking between requests on the same thread.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ..audit_context import clear_current_user
from ..logging import get_logger

logger = get_logger(__name__)


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that clears audit context after every request.

    In async web servers (uvicorn), multiple requests can share the same thread.
    Thread-local storage persists between requests, which can cause:
    - User A's context leaking into User B's request
    - Stale user IDs being written into created_by / updated_by

    Usage in app.py::

        from src.shared.infrastructure.middleware import AuditContextMiddleware

        app.add_middleware(AuditContextMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request and guarantee audit-context cleanup."""
        try:
            response = await call_next(request)
            return response
        finally:
            # Always clear, even on exceptions.
            clear_current_user()

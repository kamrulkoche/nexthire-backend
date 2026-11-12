"""Exception handler registry.

Handlers register themselves here at import time; ``apply_to_app`` then binds
them all onto the FastAPI instance in one pass. This is the same indirection
sp-company-backend uses: it lets generic handlers register first and
module-specific ones register on top, with a single deterministic application
point in the app factory.
"""

from typing import Callable, Dict, Type

from fastapi import FastAPI

from ..infrastructure.logging import get_logger

logger = get_logger(__name__)

# Exception class -> handler callable
_handlers: Dict[Type[Exception], Callable] = {}


def register_handler(exception_class: Type[Exception], handler: Callable) -> None:
    """Register a handler for an exception class.

    A later registration for the same class replaces the earlier one, so
    module-specific handlers registered after the generics win.

    Args:
        exception_class: The exception type to handle
        handler: async (Request, Exception) -> Response
    """
    _handlers[exception_class] = handler


def apply_to_app(app: FastAPI) -> None:
    """Bind every registered handler onto the FastAPI app.

    Args:
        app: The FastAPI application instance
    """
    for exception_class, handler in _handlers.items():
        app.add_exception_handler(exception_class, handler)
    logger.info(f"Registered {len(_handlers)} exception handler(s)")


def registered_count() -> int:
    """Return how many handlers are currently registered (used in tests)."""
    return len(_handlers)

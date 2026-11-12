"""Exception handlers.

``register_all_exception_handlers()`` is called once from the app factory,
before ``exception_registry.apply_to_app(app)``.
"""

from .business_handlers import register_business_exception_handlers
from .generic_handlers import register_generic_exception_handlers


def register_all_exception_handlers() -> None:
    """Register every shared handler.

    Generics first so a module-specific handler registered later can override
    one of them.
    """
    register_generic_exception_handlers()
    register_business_exception_handlers()


__all__ = [
    "register_all_exception_handlers",
    "register_business_exception_handlers",
    "register_generic_exception_handlers",
]

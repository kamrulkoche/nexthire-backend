"""Shared domain exceptions.

Every use case raises one of these rather than an HTTPException. The mapping to
status codes lives in ``src/shared/api/exception_handlers/``.
"""

from .already_exists_error import AlreadyExistsError
from .domain_exception import DomainException
from .external_service_error import ExternalServiceError
from .forbidden_error import ForbiddenError
from .not_found_error import NotFoundError
from .quota_exceeded_error import QuotaExceededError
from .repository_error import RepositoryError
from .unauthorized_error import UnauthorizedError
from .validation_error import ValidationError

__all__ = [
    "AlreadyExistsError",
    "DomainException",
    "ExternalServiceError",
    "ForbiddenError",
    "NotFoundError",
    "QuotaExceededError",
    "RepositoryError",
    "UnauthorizedError",
    "ValidationError",
]

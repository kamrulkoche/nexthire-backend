"""
User repository — queries behind sign-in and user management.

Extends BaseRepository with the lookups hgs-backend's AdminUserRepository has,
plus the paginated account list the Users screen needs.
"""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple, Type
from uuid import UUID

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import (
    contains_ci,
    equals_ci,
    resolve_sort_column,
    sort_spec,
)

from ...domain.entities.user import User
from ...domain.enums.user_role import UserRole
from ...domain.enums.user_status import UserStatus

#: Columns the account list may be sorted by — see `resolve_sort_column`.
SORTABLE = {"name", "email", "role", "status", "created_at", "last_login_at"}

DEFAULT_SORT = "name"


class UserRepository(BaseRepository[User]):
    """Repository for User database operations."""

    def __init__(self, session: MongoSession, model: Type[User] = User):
        """Initialize user repository."""
        super().__init__(session, model)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by email address (case-insensitive).

        The login lookup. The field is normalized to lowercase on write by the
        entity validator, and the needle is lowered here, so "Seeker@Home.com"
        still matches.
        """
        try:
            needle = email.lower().strip()
            return self.load(self.collection.find_one({"email": needle}))
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="get_by_email", message=str(e)
            ) from e

    async def exists_by_email(
        self, email: str, exclude_id: Optional[UUID] = None
    ) -> bool:
        """
        Check whether a user with this email exists.

        Args:
            email: Email address
            exclude_id: Ignore this document — the user's own ID on update
        """
        try:
            query: dict[str, Any] = {"email": equals_ci(email.strip())}
            if exclude_id:
                query["_id"] = {"$ne": exclude_id}
            return self.collection.count_documents(query, limit=1) > 0
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="exists_by_email", message=str(e)
            ) from e

    async def touch_last_login(self, user: User) -> User:
        """
        Record a successful login.

        Deliberately NOT through ``BaseRepository.update``: that also bumps
        ``updated_at``, which would make every sign-in look like a profile edit.
        """
        try:
            user.last_login_at = datetime.now(UTC)
            self.session.add(user)
            self.session.commit()
            return user
        except Exception as e:
            self.session.rollback()
            raise RepositoryError(
                entity_name="User", operation="touch_last_login", message=str(e)
            ) from e

    async def count_active_admins(self, exclude_id: Optional[UUID] = None) -> int:
        """
        Count admins who can still sign in.

        Used to refuse the change that would leave nobody able to manage accounts.
        """
        try:
            query: dict[str, Any] = {
                "is_active": True,
                "role": UserRole.ADMIN.value,
                "status": UserStatus.ACTIVE.value,
            }
            if exclude_id:
                query["_id"] = {"$ne": exclude_id}
            return int(self.collection.count_documents(query))
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="count_active_admins", message=str(e)
            ) from e

    async def active_admin_ids(self) -> List[UUID]:
        """Ids of every admin who can sign in — the recipients of admin alerts."""
        try:
            cursor = self.collection.find(
                {
                    "is_active": True,
                    "role": UserRole.ADMIN.value,
                    "status": UserStatus.ACTIVE.value,
                },
                {"_id": 1},
            )
            return [doc["_id"] for doc in cursor]
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="active_admin_ids", message=str(e)
            ) from e

    async def counts_by_role(self) -> Dict[str, int]:
        """``{role: count}`` over live accounts, for the admin dashboard."""
        try:
            rows = self.collection.aggregate(
                [
                    {"$match": {"is_active": True}},
                    {"$group": {"_id": "$role", "count": {"$sum": 1}}},
                ]
            )
            return {str(row["_id"]): int(row["count"]) for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="counts_by_role", message=str(e)
            ) from e

    async def list_paginated(
        self,
        params: ListQueryParams,
        *,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
    ) -> Tuple[List[User], int]:
        """
        List accounts for the Users screen.

        Returns:
            ``(rows_for_this_page, total_matching_rows)``
        """
        try:
            query: dict[str, Any] = {"is_active": True}
            if role is not None:
                query["role"] = role.value
            if status is not None:
                query["status"] = status.value

            term = params.normalized_search
            if term:
                query["$or"] = [
                    {"name": contains_ci(term)},
                    {"email": contains_ci(term)},
                ]

            total = self.collection.count_documents(query)
            field = resolve_sort_column(params.sort, SORTABLE, DEFAULT_SORT)
            cursor = (
                self.collection.find(query)
                .sort(sort_spec(field, params.order, "created_at"))
                .skip(params.offset)
                .limit(params.limit)
            )
            return self.load_many(cursor), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="User", operation="list_paginated", message=str(e)
            ) from e

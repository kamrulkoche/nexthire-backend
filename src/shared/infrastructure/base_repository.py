"""Base repository over one MongoDB collection.

Provides a standardized base repository that all module-specific repositories
extend. Subclasses query ``self.collection`` with PyMongo and turn documents
into entities with ``self.load`` / ``self.load_many``.

Every method wraps its body in try/except and re-raises ``RepositoryError`` so
a caller never sees a raw driver exception. ``DuplicateKeyError`` is
deliberately re-raised unchanged so a caller can map a unique-index collision
onto a domain-specific ``AlreadyExistsError``.
"""

from datetime import UTC, datetime
from typing import Any, Generic, Iterable, List, Optional, Type, TypeVar
from uuid import UUID

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from ..domain.entities.document import MongoDocument
from ..domain.exceptions.repository_error import RepositoryError
from .database import MongoSession

TEntity = TypeVar("TEntity", bound=MongoDocument)


class BaseRepository(Generic[TEntity]):
    """Generic CRUD repository for a MongoDocument entity.

    Constructed as ``Repo(session, EntityClass)`` — the entity class is passed
    explicitly, matching the reference project's convention.
    """

    def __init__(self, session: MongoSession, model: Type[TEntity]):
        """Initialize the repository.

        Args:
            session: Active MongoSession
            model: Entity class this repository manages
        """
        self.session = session
        self.model = model

    @property
    def collection(self) -> Collection:
        """The collection this repository's entity lives in."""
        return self.session.collection(self.model)

    def load(self, document: Optional[dict[str, Any]]) -> Optional[TEntity]:
        """A raw document as this repository's entity."""
        return self.session.load(self.model, document)

    def load_many(self, documents: Iterable[dict[str, Any]]) -> List[TEntity]:
        """Raw documents as this repository's entities."""
        return self.session.load_many(self.model, documents)

    def _error(self, operation: str, e: Exception) -> RepositoryError:
        return RepositoryError(
            entity_name=self.model.__name__, operation=operation, message=str(e)
        )

    async def create(self, entity: TEntity) -> TEntity:
        """Persist a new entity.

        Raises:
            DuplicateKeyError: On a unique-index violation (caller maps it)
            RepositoryError: On any other database failure
        """
        try:
            self.session.add(entity)
            self.session.commit()
            return entity
        except DuplicateKeyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            raise self._error("create", e) from e

    async def get_by_id(self, entity_id: UUID) -> Optional[TEntity]:
        """Fetch one entity by id, or None."""
        try:
            return self.load(self.collection.find_one({"_id": entity_id}))
        except Exception as e:
            raise self._error("get_by_id", e) from e

    async def get_all(self, is_active: Optional[bool] = None) -> List[TEntity]:
        """Fetch all entities, optionally filtered by the soft-delete flag."""
        try:
            query: dict[str, Any] = {}
            if is_active is not None and "is_active" in self.model.model_fields:
                query["is_active"] = is_active
            return self.load_many(self.collection.find(query))
        except Exception as e:
            raise self._error("get_all", e) from e

    async def update(self, entity: TEntity) -> TEntity:
        """Persist changes to an existing entity, refreshing ``updated_at``.

        Raises:
            DuplicateKeyError: On a unique-index violation (caller maps it)
            RepositoryError: On any other database failure
        """
        try:
            if "updated_at" in type(entity).model_fields:
                entity.updated_at = datetime.now(UTC)
            self.session.add(entity)
            self.session.commit()
            return entity
        except DuplicateKeyError:
            self.session.rollback()
            raise
        except Exception as e:
            self.session.rollback()
            raise self._error("update", e) from e

    async def soft_delete(self, entity_id: UUID) -> bool:
        """Mark an entity inactive rather than removing the document.

        Returns:
            True if a document was deactivated, False if none matched
        """
        if "is_active" not in self.model.model_fields:
            raise RepositoryError(
                entity_name=self.model.__name__,
                operation="soft_delete",
                message="Model has no is_active field",
            )
        try:
            values: dict[str, Any] = {"is_active": False}
            if "updated_at" in self.model.model_fields:
                values["updated_at"] = datetime.now(UTC)
            result = self.collection.update_one({"_id": entity_id}, {"$set": values})
            return result.matched_count > 0
        except Exception as e:
            raise self._error("soft_delete", e) from e

    async def count(self, is_active: Optional[bool] = None) -> int:
        """Count entities, optionally filtered by the soft-delete flag."""
        try:
            query: dict[str, Any] = {}
            if is_active is not None and "is_active" in self.model.model_fields:
                query["is_active"] = is_active
            return int(self.collection.count_documents(query))
        except Exception as e:
            raise self._error("count", e) from e

    async def exists_by_id(self, entity_id: UUID) -> bool:
        """Check whether a document with this id exists."""
        try:
            return self.collection.count_documents({"_id": entity_id}, limit=1) > 0
        except Exception as e:
            raise self._error("exists_by_id", e) from e

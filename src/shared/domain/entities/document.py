"""The base every persisted entity extends: a Pydantic model mapped to a
MongoDB collection.

An entity declares::

    class Job(AuditedEntity):
        __collection__ = "jobs"
        __indexes__ = [
            IndexModel([("source_id", 1), ("external_id", 1)], unique=True,
                       name="uq_jobs_source_external"),
        ]

``id`` is stored as the document's ``_id`` (a BSON UUID). Enums are stored
by VALUE ("seeker", not "SEEKER"); a ``date`` is stored as a UTC-midnight
datetime, because BSON has no date-only type.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, ClassVar, Optional, Type, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr
from pymongo import IndexModel

TDoc = TypeVar("TDoc", bound="MongoDocument")

_REGISTRY: dict[str, Type["MongoDocument"]] = {}


def to_bson(value: Any) -> Any:
    """A Python value as something BSON can store.

    Used for documents AND for query values, so a filter on an enum or a
    date matches what was written.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, dict):
        return {k: to_bson(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_bson(v) for v in value]
    if isinstance(value, BaseModel):
        return to_bson(value.model_dump())
    return value


class MongoDocument(BaseModel):
    """A Pydantic model that is persisted as one MongoDB document.

    ``_snapshot`` holds the document as it was last read or written, so the
    session can write only the fields that changed (see ``MongoSession``).
    """

    __collection__: ClassVar[str] = ""
    __indexes__: ClassVar[list[IndexModel]] = []

    #: Stored as ``_id``. Redeclared (with a description) by the base entities.
    id: UUID = Field(default_factory=uuid4)

    _snapshot: Optional[dict[str, Any]] = PrivateAttr(default=None)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__dict__.get("__collection__")
        if name:
            _REGISTRY[name] = cls

    def to_document(self) -> dict[str, Any]:
        """This entity as a BSON-ready dict, ``id`` renamed to ``_id``."""
        data = to_bson(self.model_dump())
        data["_id"] = data.pop("id")
        return data

    @classmethod
    def from_document(cls: Type[TDoc], document: dict[str, Any]) -> TDoc:
        """An entity from a stored document, with its change snapshot."""
        data = dict(document)
        data["id"] = data.pop("_id")
        known = {k: v for k, v in data.items() if k in cls.model_fields}
        entity = cls.model_validate(known)
        entity._snapshot = entity.to_document()
        return entity


def registered_documents() -> list[Type[MongoDocument]]:
    """Every entity class that names a collection, in definition order."""
    return list(_REGISTRY.values())

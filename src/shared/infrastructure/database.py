"""MongoDB client, the per-request session and index bootstrapping.

NextHire AI stores everything in one MongoDB database (``MONGODB_DB``) reached
through ``MONGODB_URL``. Locally that is the ``mongo`` service in
``docker-compose.yml``.

Schema ownership: there is no migration tool. Each entity declares its
collection and its indexes (``MongoDocument.__collection__`` /
``__indexes__``), and ``ensure_indexes`` creates any that are missing on
startup. ``create_index`` is idempotent, so running it every boot is safe.

The session object (``MongoSession``) keeps the unit-of-work shape the
repositories and use cases were written against — ``add`` / ``commit`` /
``refresh`` / ``rollback`` — so the same call sites work on MongoDB. It is NOT
transactional: a standalone MongoDB has no multi-document transactions, and
every write path here already commits one logical change at a time.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from datetime import UTC
from typing import Any, Callable, Generator, Optional, Type, TypeVar
from uuid import UUID

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from ..domain.entities.document import MongoDocument, registered_documents
from ..utils.config import settings

TDoc = TypeVar("TDoc", bound=MongoDocument)

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """The process-wide client, created on first use.

    Lazy so that importing this module (tests, scripts, ``--help``) never
    opens a connection. ``tz_aware`` returns UTC-aware datetimes, which every
    comparison in the code base assumes; ``standard`` stores UUIDs as BSON
    binary subtype 4.
    """
    global _client
    if _client is None:
        _client = MongoClient(
            settings.mongodb_url,
            tz_aware=True,
            tzinfo=UTC,
            uuidRepresentation="standard",
            serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
            maxPoolSize=settings.mongodb_max_pool_size,
        )
    return _client


def get_database() -> Database:
    """This service's database."""
    return get_client()[settings.mongodb_db]


class MongoSession:
    """A thin unit of work over a MongoDB ``Database``.

    - ``add(entity)`` stages an entity; ``commit()`` writes every staged one.
      A new entity (never loaded or written) is INSERTED, so a duplicate key
      raises ``pymongo.errors.DuplicateKeyError``. A loaded entity is written
      as a ``$set`` of only the fields that changed since it was loaded, the
      way SQLAlchemy flushes only dirty columns — so a stale copy never
      clobbers a field another writer changed atomically (a run claim, a
      counter).
    - ``delete(entity)`` stages a removal by id.
    - ``rollback()`` drops whatever is staged.
    - ``refresh(entity)`` re-reads the entity's fields from the database.

    Repositories reach collections through ``collection(Model)`` and query
    them directly; ``load``/``load_many`` turn raw documents into entities
    with a change-tracking snapshot.
    """

    def __init__(self, db: Database):
        self.db = db
        self._pending: list[MongoDocument] = []
        self._deletes: list[MongoDocument] = []

    # -- collections and loading -------------------------------------------

    def collection(self, model: Type[MongoDocument]) -> Collection:
        """The collection an entity class lives in."""
        return self.db[model.__collection__]

    def load(
        self, model: Type[TDoc], document: Optional[dict[str, Any]]
    ) -> Optional[TDoc]:
        """A raw document as an entity (None stays None)."""
        if document is None:
            return None
        return model.from_document(document)

    def load_many(self, model: Type[TDoc], documents: Any) -> list[TDoc]:
        """Raw documents (a cursor or a list) as entities."""
        return [model.from_document(d) for d in documents]

    def get(self, model: Type[TDoc], entity_id: UUID) -> Optional[TDoc]:
        """One entity by id, or None."""
        return self.load(model, self.collection(model).find_one({"_id": entity_id}))

    # -- unit of work -------------------------------------------------------

    def add(self, entity: MongoDocument) -> None:
        """Stage an insert (new entity) or an update (loaded entity)."""
        if not any(e is entity for e in self._pending):
            self._pending.append(entity)

    def add_all(self, entities: list[MongoDocument]) -> None:
        """Stage several entities."""
        for entity in entities:
            self.add(entity)

    def delete(self, entity: MongoDocument) -> None:
        """Stage a removal."""
        self._deletes.append(entity)

    def flush(self) -> None:
        """Alias of ``commit`` — there is no separate flush on MongoDB."""
        self.commit()

    def commit(self) -> None:
        """Write everything staged, in the order it was staged.

        On a failure the rest of the batch is dropped and the error re-raised,
        matching what a rolled-back SQL transaction leaves behind as closely
        as a non-transactional store can.
        """
        pending, self._pending = self._pending, []
        deletes, self._deletes = self._deletes, []
        for entity in pending:
            self._write(entity)
        for entity in deletes:
            self.collection(type(entity)).delete_one({"_id": entity.id})

    def rollback(self) -> None:
        """Drop staged writes."""
        self._pending.clear()
        self._deletes.clear()

    def refresh(self, entity: MongoDocument) -> None:
        """Re-read an entity's fields from its document."""
        document = self.collection(type(entity)).find_one({"_id": entity.id})
        if document is None:
            return
        fresh = type(entity).from_document(document)
        for name in type(entity).model_fields:
            object.__setattr__(entity, name, getattr(fresh, name))
        entity._snapshot = fresh._snapshot

    def close(self) -> None:
        """Drop staged writes; the client itself is pooled and stays open."""
        self.rollback()

    def _write(self, entity: MongoDocument) -> None:
        collection = self.collection(type(entity))
        document = entity.to_document()
        snapshot = entity._snapshot
        if snapshot is None:
            collection.insert_one(document)
        else:
            changed = {
                k: v for k, v in document.items() if k != "_id" and snapshot.get(k) != v
            }
            if changed:
                collection.update_one({"_id": entity.id}, {"$set": changed})
        entity._snapshot = document


def get_db() -> Generator[MongoSession, None, None]:
    """FastAPI dependency yielding a session over this service's database."""
    session = MongoSession(get_database())
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_context() -> Generator[MongoSession, None, None]:
    """Context-managed session for use outside a request (startup, scripts).

    Staged writes are committed on success and dropped on error.
    """
    session = MongoSession(get_database())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


#: Something that opens a session as a context manager — ``get_db_context``
#: in production. Background work (a collection run after its request has
#: ended) takes one of these instead of a session.
SessionFactory = Callable[[], AbstractContextManager[MongoSession]]


def get_session_factory() -> SessionFactory:
    """FastAPI dependency returning how background work opens its session.

    Tests override this so background work runs against the test database.
    """
    return get_db_context


def discover_entities() -> None:
    """Import entity modules so every collection's indexes are registered.

    An explicit list: it fails loudly if a module is renamed, where a glob
    would silently skip it. Every entity package must be listed here.
    """
    import src.modules.collection.domain.entities  # noqa: F401
    import src.modules.job.domain.entities  # noqa: F401
    import src.modules.job_source.domain.entities  # noqa: F401
    import src.modules.lead_finder.domain.entities  # noqa: F401
    import src.modules.notification.domain.entities  # noqa: F401
    import src.modules.preference.domain.entities  # noqa: F401
    import src.modules.recommendation.domain.entities  # noqa: F401
    import src.modules.saved_job.domain.entities  # noqa: F401
    import src.modules.tracker.domain.entities  # noqa: F401
    import src.modules.user.domain.entities  # noqa: F401


def ensure_indexes(db: Optional[Database] = None) -> None:
    """Create every declared index that does not exist yet.

    Replaces the Alembic revision check. Idempotent: ``create_index`` on an
    existing, identical index is a no-op. An index whose options CHANGED
    under the same name raises — drop the old one by hand, deliberately.
    """
    discover_entities()
    database = db if db is not None else get_database()
    for model in registered_documents():
        if model.__indexes__:
            database[model.__collection__].create_indexes(list(model.__indexes__))


def init_db(db: Optional[Database] = None) -> None:
    """Prepare a database for use — for tests and standalone scripts."""
    ensure_indexes(db)


def close_db() -> None:
    """Close the client's connection pool on shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None

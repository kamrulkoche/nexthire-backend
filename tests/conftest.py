"""Root test configuration.

Sets ``ENVIRONMENT=test`` BEFORE anything under `src/` is imported. The config
loader reads it at import time to pick `config/.env.test` and to skip the
developer's root `.env`, so the suite never sees a real DATABASE_URL — it
builds its own SQLite databases instead (see `tests/integration/conftest.py`).
"""

import os

os.environ["ENVIRONMENT"] = "test"


# mongomock validates every write by BSON-encoding it with pymongo's default
# codec options, whose UUID representation is UNSPECIFIED — so a native
# uuid.UUID (every _id here) is refused, although the real client is
# configured with uuidRepresentation="standard". Encode with the same options
# the application uses. Validation only: mongomock stores the Python objects.
import bson  # noqa: E402
import mongomock.collection  # noqa: E402
from bson.binary import UuidRepresentation  # noqa: E402
from bson.codec_options import CodecOptions  # noqa: E402

_STANDARD = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)


class _StandardUuidBSON:
    @staticmethod
    def encode(document, check_keys=False, codec_options=None):  # type: ignore[no-untyped-def]
        return bson.encode(document, check_keys, _STANDARD)


mongomock.collection.BSON = _StandardUuidBSON  # type: ignore[attr-defined,assignment]

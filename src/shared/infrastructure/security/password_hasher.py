"""Password hashing for user accounts (admins and seekers).

Uses bcrypt directly. There is no equivalent module in sp-company-backend —
Clerk owned credential storage there, so that repo has no hashing at all and
its only `verify_password` calls are remote Clerk API calls.

Deliberately NOT using passlib: its last release was 2020, and it reads
``bcrypt.__about__.__version__``, which bcrypt 5.x removed — the combination
emits an AttributeError trap on first hash.

bcrypt notes that matter:
  - The algorithm silently truncates input at 72 BYTES. A caller passing a
    longer passphrase would get a hash covering only the first 72 bytes, so
    ``hash_password`` rejects it loudly instead.
  - Each hash embeds its own salt and cost, so ``verify_password`` needs no
    stored parameters and an old hash keeps verifying after COST is raised.
"""

import bcrypt

from ..logging import get_logger

logger = get_logger(__name__)

#: bcrypt work factor. 12 is ~250ms on current hardware — slow enough to make
#: offline cracking expensive, fast enough for an interactive login.
COST = 12

#: bcrypt truncates beyond this many BYTES (not characters — a multi-byte UTF-8
#: passphrase hits the limit sooner than its length suggests).
MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage.

    Args:
        plain_password: The password as typed by the user

    Returns:
        The bcrypt hash, as a UTF-8 string safe to store in a text column

    Raises:
        ValueError: If the password is empty or exceeds bcrypt's 72-byte limit
    """
    if not plain_password:
        raise ValueError("Password must not be empty")

    encoded = plain_password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must not exceed {MAX_PASSWORD_BYTES} bytes "
            f"(got {len(encoded)}). bcrypt truncates beyond this, which would "
            "silently weaken the hash."
        )

    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=COST)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash.

    Never raises on a malformed hash — a corrupt stored value is a failed
    login, not a 500.

    Args:
        plain_password: The password as typed by the user
        hashed_password: The stored bcrypt hash

    Returns:
        True if the password matches
    """
    if not plain_password or not hashed_password:
        return False

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError) as exc:
        # Malformed/truncated hash in the database.
        logger.error(f"Password verification failed on a malformed hash: {exc}")
        return False

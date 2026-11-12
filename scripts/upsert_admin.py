"""Create the admin account, or reset an existing one to a known good state.

    ADMIN_EMAIL=... ADMIN_PASSWORD=... ./venv/Scripts/python.exe scripts/upsert_admin.py

The deliberate counterpart to `setup_admin_service.py`, which runs on every
boot and therefore NEVER touches an existing account. This one is run by hand,
so it may: an existing account gets a fresh password hash, the admin role and
active status. Re-running it with the same values changes nothing else.

Credentials come from the environment only, and the password must meet the
same MIN_PASSWORD_LENGTH as every other account.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.user.application.schemas.user_schema import (  # noqa: E402
    MIN_PASSWORD_LENGTH,
)
from src.modules.user.domain.entities.user import User  # noqa: E402
from src.modules.user.domain.enums.user_role import UserRole  # noqa: E402
from src.modules.user.domain.enums.user_status import UserStatus  # noqa: E402
from src.shared.infrastructure.database import get_db_context  # noqa: E402
from src.shared.infrastructure.security.password_hasher import (  # noqa: E402
    hash_password,
)
from src.shared.utils.config import settings  # noqa: E402


def upsert_admin() -> None:
    """Create or reset the admin named by ADMIN_EMAIL."""
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not email:
        raise SystemExit("Set ADMIN_EMAIL.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(
            f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    with get_db_context() as db:
        user = db.load(User, db.collection(User).find_one({"email": email}))
        if user is None:
            db.add(
                User(
                    name=settings.admin_name,
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                )
            )
            print(f"Created admin {email}.")
            return

        user.password_hash = hash_password(password)
        user.role = UserRole.ADMIN
        user.status = UserStatus.ACTIVE
        user.is_active = True
        db.add(user)  # written by get_db_context's commit
        print(f"Reset admin {email}: new password hash, role admin, status active.")


if __name__ == "__main__":
    upsert_admin()

"""Load the starter job sources and, optionally, a demo seeker.

    ./venv/Scripts/python.exe scripts/seed_demo_data.py            # write
    ./venv/Scripts/python.exe scripts/seed_demo_data.py --dry-run  # report only

Follows the rules hgs-backend's seed scripts follow:

- IDEMPOTENT, keyed by natural key — a source by slug, a user by email. A
  second run reports what it skipped and writes nothing.
- An existing document is NEVER updated. Once an admin has edited a seeded source,
  a re-run must not quietly overwrite their work.

No jobs are seeded. Jobs come from the sources: start the API (the scheduler
collects every due source within a minute) or press "Run now" on the Sources
screen. Fabricated postings would be indistinguishable from real ones.

The three starter sources need no credentials. Adzuna is not seeded because it
needs ADZUNA_APP_ID / ADZUNA_APP_KEY; add it from the Sources screen.

The demo seeker is created only when DEMO_SEEKER_PASSWORD is set, and only
outside prod. The admin is not created here — the app bootstraps it from
ADMIN_EMAIL / ADMIN_PASSWORD on startup.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modules.job_source.domain.entities.job_source import JobSource  # noqa: E402
from src.modules.job_source.domain.enums.source_type import SourceType  # noqa: E402
from src.modules.job_source.domain.services.source_config import (  # noqa: E402
    normalize_source_config,
)
from src.modules.preference.domain.entities.job_preference import (  # noqa: E402
    JobPreference,
)
from src.modules.user.application.schemas.user_schema import (  # noqa: E402
    MIN_PASSWORD_LENGTH,
)
from src.modules.user.domain.entities.user import User  # noqa: E402
from src.modules.user.domain.enums.user_role import UserRole  # noqa: E402
from src.shared.infrastructure.database import get_db_context  # noqa: E402
from src.shared.infrastructure.security.password_hasher import (  # noqa: E402
    hash_password,
)
from src.shared.utils.config import settings  # noqa: E402

SOURCES: List[Dict[str, Any]] = [
    {
        "name": "Remotive — Software development",
        "slug": "remotive-software-dev",
        "source_type": SourceType.REMOTIVE,
        "config": {"category": "software-dev"},
        "schedule_minutes": 360,
    },
    {
        "name": "Arbeitnow — All jobs",
        "slug": "arbeitnow-all",
        "source_type": SourceType.ARBEITNOW,
        "config": {"max_pages": 2},
        "schedule_minutes": 360,
    },
    {
        "name": "Remote OK — All jobs",
        "slug": "remoteok-all",
        "source_type": SourceType.REMOTEOK,
        "config": {},
        "schedule_minutes": 720,
    },
]

DEMO_SEEKER = {"name": "Demo Seeker", "email": "seeker@nexthire.dev"}

DEMO_PREFERENCES: Dict[str, Any] = {
    "keywords": ["python", "fastapi", "postgresql", "backend"],
    "excluded_keywords": ["php"],
    "locations": [],
    "remote_only": True,
    "employment_types": ["full_time", "contract"],
    "profile_summary": (
        "Backend developer with five years of Python, FastAPI and PostgreSQL. "
        "Looking for a remote backend or platform role."
    ),
}


def seed(dry_run: bool) -> None:
    """Create whatever is missing; report everything."""
    if settings.environment == "prod":
        sys.exit("Refusing to seed demo data with ENVIRONMENT=prod.")

    with get_db_context() as session:
        for spec in SOURCES:
            exists = session.collection(JobSource).find_one(
                {"slug": spec["slug"]}, {"_id": 1}
            )
            if exists:
                print(f"  skip  source {spec['slug']} (exists)")
                continue
            print(f"  {'would add' if dry_run else 'add'}  source {spec['slug']}")
            if not dry_run:
                session.add(
                    JobSource(
                        **{
                            **spec,
                            "config": normalize_source_config(
                                spec["source_type"], spec["config"]
                            ),
                        }
                    )
                )

        password = os.getenv("DEMO_SEEKER_PASSWORD") or ""
        if not password:
            print("  skip  demo seeker (DEMO_SEEKER_PASSWORD is not set)")
        elif len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(
                f"DEMO_SEEKER_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        else:
            user = session.load(
                User, session.collection(User).find_one({"email": DEMO_SEEKER["email"]})
            )
            if user is not None:
                print(f"  skip  user {DEMO_SEEKER['email']} (exists)")
            else:
                print(
                    f"  {'would add' if dry_run else 'add'}  user {DEMO_SEEKER['email']}"
                )
                if not dry_run:
                    user = User(
                        **DEMO_SEEKER,
                        password_hash=hash_password(password),
                        role=UserRole.SEEKER,
                    )
                    session.add(user)
                    session.add(JobPreference(user_id=user.id, **DEMO_PREFERENCES))

        if dry_run:
            session.rollback()
            print("Dry run — nothing written.")
        else:
            print("Done.")


def main() -> None:
    """Parse arguments and seed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    seed(parser.parse_args().dry_run)


if __name__ == "__main__":
    main()

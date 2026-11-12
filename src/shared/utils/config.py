"""Application configuration using Pydantic Settings.

Configuration is loaded in order (later overrides earlier):
1. config/.env.base (common settings for all environments)
2. config/.env.{environment} (environment-specific: dev, test, prod)
3. .env file (local development overrides - gitignored)

The same loader as hgs-backend, which took it from sp-company-backend. The
reference's fourth layer, AWS Secrets Manager, is omitted for the same reason
HGS omits it: no AWS account is wired up, so secrets come from the environment.
"""

import json
import os
from pathlib import Path
from typing import Annotated, List, Optional

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Project root: this file lives at src/shared/utils/config.py, hence parent x 4.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

#: Minimum SECRET_KEY length outside dev. RFC 7518 section 3.2 requires an HMAC
#: key of at least the hash output size (32 bytes for SHA-256); PyJWT emits an
#: InsecureKeyLengthWarning below it.
MIN_SECRET_KEY_BYTES = 32

#: Environments that may run on the placeholder SECRET_KEY. `test` is here so
#: the suite does not need a real secret; it never serves traffic.
_RELAXED_ENVIRONMENTS = {"dev", "test"}

# Get ENVIRONMENT from the OS first (set on the server, default dev for local).
_environment = os.getenv("ENVIRONMENT", "dev").lower()

# 1. Base config (common to all environments)
_base_config = PROJECT_ROOT / "config" / ".env.base"
if _base_config.exists():
    load_dotenv(_base_config)

# 2. Environment-specific config
_env_config = PROJECT_ROOT / "config" / f".env.{_environment}"
if _env_config.exists():
    load_dotenv(_env_config, override=True)

# 3. Root .env — local developer overrides (gitignored). Highest-priority file
#    so a developer can override any base/env value without editing the shared,
#    committed config files. This is where MONGODB_URL and SECRET_KEY live
#    locally.
#
#    Skipped under `test`: the suite must run against its own SQLite database
#    whatever a developer's .env points at.
_root_env = PROJECT_ROOT / ".env"
if _root_env.exists() and _environment != "test":
    load_dotenv(_root_env, override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Field names are snake_case; the corresponding env vars are the uppercase
    form (``MONGODB_URL`` -> ``mongodb_url``), matching pydantic-settings'
    case-insensitive lookup.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "NextHire AI Backend"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "dev"

    # Server. 8002: hgs-backend takes 8000 and homesprit-backend 8001 on the
    # same machine.
    host: str = "127.0.0.1"
    port: int = 8002

    # Database — a dedicated MongoDB database (the `mongo` service in
    # docker-compose.yml locally). Nothing else writes to it.
    mongodb_url: str = "mongodb://localhost:27018"
    mongodb_db: str = "nexthire"
    mongodb_timeout_ms: int = 5000
    mongodb_max_pool_size: int = 20

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/app.log"

    # Security / JWT
    # SECRET_KEY signs every access token. Changing it invalidates all
    # outstanding sessions, which is the intended "log everyone out" lever.
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    # A working week. HGS uses a year so its single admin is never signed out
    # mid-edit; NextHire AI has self-registered users, so a
    # shorter session is the better trade. What makes it safe either way is
    # the per-request check: `hasAccess` re-reads the user row, so
    # deactivating an account takes effect on their next request.
    #
    # The frontend's session cookie takes its max-age from `expires_in` on the
    # login response, so the two can never disagree.
    access_token_expire_minutes: int = 10080

    # CORS — the Next.js site's origin. The browser never calls this service
    # (the frontend proxies server-side), so this matters only for /docs and
    # for anyone pointing a browser client here directly. Credentials are
    # allowed, so it can never be "*".
    #
    # `NoDecode` is required, not decorative: pydantic-settings JSON-decodes
    # List[str] fields from the environment BEFORE validators run, so a bare
    # `CORS_ORIGINS=http://localhost:3003` would fail at import.
    cors_origins: Annotated[List[str], NoDecode] = ["http://localhost:3003"]

    # Initial admin bootstrap (see scripts/setup_admin_service.py).
    # Never hardcode these; they are read from the environment only.
    setup_admin: bool = True
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    admin_name: str = "NextHire AI Admin"

    # Gemini — the only AI provider. Server-side only; the frontend never sees
    # the key. With no key, recommendations fall back to the heuristic scorer
    # (see modules/recommendation), so the feature still works offline.
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 45.0
    # Jobs sent to Gemini in one scoring call, and so the most one refresh can
    # cost. Candidates are pre-filtered in SQL first.
    recommendation_batch_size: int = 15
    # Matches at or above this score raise a notification after a run.
    recommendation_notify_score: int = 70

    # Scheduled collection (shared/infrastructure/tasks/scheduler.py). One API
    # process runs it; any second replica sets SCHEDULER_ENABLED=false.
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 60
    # How long a claimed source stays locked. A run that crashes without
    # releasing its claim frees the source again after this.
    collection_lock_minutes: int = 15
    # A job not seen by its source for this many days is marked inactive.
    job_stale_after_days: int = 30
    # Upper bound on the jobs one connector call may return.
    collection_max_jobs_per_run: int = 500

    # Outbound HTTP for connectors.
    connector_timeout_seconds: float = 20.0
    connector_max_bytes: int = 10 * 1024 * 1024
    connector_user_agent: str = "NextHireAI/1.0 (+job collector)"

    # Adzuna — only needed for sources of type `adzuna`.
    adzuna_app_id: Optional[str] = None
    adzuna_app_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Lead Finder — Google Maps Platform, Places API (New).
    # ------------------------------------------------------------------
    # Server-side key with the Places API (New) enabled. Sent in the
    # `X-Goog-Api-Key` header, never a URL, never to the browser. The map in
    # the browser uses a SEPARATE, referrer-restricted key configured in the
    # frontend (NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY).
    google_maps_api_key: Optional[str] = None
    places_timeout_seconds: float = 20.0
    # Attempts per request on 429 / 5xx / transport errors (exponential backoff).
    places_max_attempts: int = 3
    # Text Search returns at most 20 places a page and 60 a query; 3 pages is
    # everything Google will give for one query.
    places_max_pages_per_query: int = 3
    # Content retention. Google Maps Platform terms let a place ID be stored
    # indefinitely; other Places content may only be kept temporarily. After
    # this many days every Google-sourced field on a lead is wiped by the
    # scheduler, leaving the place ID (and the user's own notes and status),
    # and "Refresh" re-reads it from Place Details. Review against the terms
    # that apply to your account before raising it.
    lead_content_ttl_days: int = 30
    # Defaults for the admin-editable Lead Finder settings row, used when the
    # row is first created.
    lead_daily_request_quota: int = 300
    lead_max_requests_per_search: int = 90
    # Searches a lead finder may START per hour (in-process limiter).
    lead_searches_per_hour: int = 30

    # Sign-in / registration attempt limits ("Too many attempts"). Setting this
    # false switches them off for local development; it is IGNORED outside the
    # relaxed environments (dev, test), so production always enforces them.
    auth_rate_limit_enabled: bool = True

    @property
    def auth_rate_limit_active(self) -> bool:
        """Whether sign-in / registration attempt limits are enforced."""
        return (
            self.auth_rate_limit_enabled
            or self.environment.lower() not in _RELAXED_ENVIRONMENTS
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from a JSON array or a comma-separated string."""
        if isinstance(v, str):
            if v.startswith("["):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Refuse to start a deployed environment on a weak signing key.

        Two separate failures are caught:

        - The placeholder key, which anyone reading this repo could use to mint
          a valid token.
        - Any key shorter than the HMAC block size (RFC 7518 §3.2).
        """
        environment = os.getenv("ENVIRONMENT", "dev").lower()
        if environment in _RELAXED_ENVIRONMENTS:
            return v

        generate_hint = (
            'Generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(48))"'
        )

        if v == "change-me-in-production":
            raise RuntimeError(
                f"SECRET_KEY must be set to a real value outside dev. {generate_hint}"
            )

        if len(v.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
            raise RuntimeError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes "
                f"(got {len(v.encode('utf-8'))}). RFC 7518 requires this for "
                f"HS256. {generate_hint}"
            )

        return v


# Global settings instance — imported as `from src.shared.utils.config import settings`
settings = Settings()

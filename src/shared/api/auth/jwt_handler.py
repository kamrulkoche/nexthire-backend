"""JWT minting and verification.

THIS IS THE ONLY PROVIDER-SPECIFIC SEAM in the auth stack.

Ported from hgs-backend. sp-company-backend's equivalent verifies a
Clerk-issued RS256 token against Clerk's JWKS endpoint; HGS, and NextHire AI
after it, issue their own HS256 tokens signed with ``settings.secret_key``. Everything downstream — the
``hasAccess`` dependency, the role checks, the audit-context stamping — consumes
the same extracted context dict and is unchanged.

Swapping to Clerk later means rewriting ``verify_access_token`` and
``extract_user_context`` here, and nothing else.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from ...infrastructure.logging import get_logger
from ...utils.config import settings

logger = get_logger(__name__)


def create_access_token(user_id: UUID, email: str, role: str) -> str:
    """Mint a signed access token for an authenticated user.

    Claims follow registered-claim conventions so a future move to a real
    identity provider is a drop-in: ``sub`` carries the user id, ``exp``/``iat``
    bound the lifetime.

    Args:
        user_id: User's database UUID
        email: User's email (convenience claim, not authoritative)
        role: User's role value (cross-checked against the DB on every request)

    Returns:
        Encoded JWT string
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def verify_access_token(token: str) -> Dict[str, Any]:
    """Verify a token's signature and expiry, returning its claims.

    ``require`` forces the presence of the claims we depend on, so a token
    missing ``exp`` can never be treated as non-expiring.

    Args:
        token: The raw JWT (no "Bearer " prefix)

    Returns:
        Decoded claims

    Raises:
        HTTPException: 401 if the token is expired, malformed or badly signed
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["sub", "exp", "iat"],
            },
            # Small leeway so a few seconds of clock skew between the API host
            # and the token issuer does not reject a freshly minted token.
            leeway=10,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError as exc:
        logger.warning(f"Rejected an invalid token: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def extract_user_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the fields the auth dependency needs out of a verified payload.

    Mirrors the shape of sp-company-backend's
    ``extract_user_context_from_jwt`` so the consuming dependency is identical.

    Args:
        payload: Verified JWT claims

    Returns:
        ``{"user_id": UUID, "email": str, "role": str}``

    Raises:
        HTTPException: 401 if ``sub`` is not a valid UUID
    """
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return {
        "user_id": user_id,
        "email": payload.get("email", ""),
        "role": payload.get("role", ""),
    }

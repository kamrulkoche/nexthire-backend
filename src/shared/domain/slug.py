"""The slug rule, in one place.

A slug is a stable, URL-safe identifier — here, a job source's (`remotive-dev`).
Ported unchanged from hgs-backend, where five entities share it; here only
`JobSource` carries one today, but the rule is the same and so is the module.

The rule has to be applied at TWO layers, and for different reasons:

- On the request schema, so a malformed slug is rejected by FastAPI as a 422
  naming the field, before any use case runs.
- On the entity, so the same value cannot reach the database through a code
  path that skipped the schema — a seed script, a test, a future internal
  caller.

Without the schema layer the entity's ValueError surfaces from inside the use
case as an unhandled pydantic error and the API answers 500 for what is plainly
a bad request. Without the entity layer the database would accept `Hello
World!` as a URL segment.
"""

_ALLOWED_EXTRA = "-"


def normalize_slug(value: str) -> str:
    """Normalize a slug and reject anything a URL would mangle.

    Lowercased rather than merely checked, so "SP-Company" and "sp-company"
    collide on the unique index instead of becoming two pages for one thing.

    Args:
        value: Raw slug from a form or a fixture

    Returns:
        The trimmed, lowercased slug

    Raises:
        ValueError: If the slug is empty, or holds anything but letters,
            numbers and hyphens. Spaces, slashes, accents and punctuation are
            all rejected rather than transliterated: silently rewriting
            someone's slug means the URL they were shown is not the URL they
            get.
    """
    normalized = value.strip().lower()

    if not normalized:
        raise ValueError("Slug must not be empty")

    if not all(char.isalnum() or char in _ALLOWED_EXTRA for char in normalized):
        raise ValueError(
            f"Slug may contain only letters, numbers and hyphens: got {value!r}"
        )

    return normalized

"""The per-type rules for a source's ``config``.

``job_sources.config`` is JSON because its keys differ by source type. That
generality is the reason it needs one strict gate: every config is normalized
here, against an allowlist of keys per type, before it is stored. A key this
file does not know is refused, not carried — a typo in a field name should be a
422 the admin sees, not a silently ignored setting.

Applied on the request schemas (so FastAPI answers 422 naming the field) and
again by the use cases (so a seed script cannot bypass it) — the two-layer
rule hgs-backend applies to slugs.

Pure functions, no I/O: the URL check here is SHAPE only. Whether the host
resolves to a private address is checked at fetch time, in the connector,
because DNS can change between saving a source and running it.
"""

from typing import Any
from urllib.parse import urlparse

from ..enums.source_type import SourceType

#: Fields a JSON feed's ``field_map`` may name. Each maps to a dotted path
#: inside one item of the feed.
JSON_FIELD_MAP_KEYS = {
    "id",
    "title",
    "company",
    "location",
    "url",
    "description",
    "posted_at",
    "tags",
    "salary_min",
    "salary_max",
    "remote",
}

#: Field-map keys a JSON feed cannot work without.
JSON_FIELD_MAP_REQUIRED = {"title", "url"}

_MAX_TEXT = 200
_MAX_PAGES = 5


def _text(config: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    """Read an optional short string, stripped; blank becomes None."""
    value = config.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be text")
    value = value.strip()
    if len(value) > _MAX_TEXT:
        raise ValueError(f"'{key}' must be at most {_MAX_TEXT} characters")
    return value


def _feed_url(config: dict[str, Any]) -> str:
    """Read a required http(s) URL."""
    url = _text(config, "url", required=True)
    assert url is not None  # required=True guarantees it
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("'url' must be an http:// or https:// address")
    if parsed.username or parsed.password:
        raise ValueError("'url' must not carry credentials")
    return url


def _pages(config: dict[str, Any]) -> int:
    """Read ``max_pages``, 1 by default, capped so one run stays polite."""
    value = config.get("max_pages", 1)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("'max_pages' must be a whole number")
    if not 1 <= value <= _MAX_PAGES:
        raise ValueError(f"'max_pages' must be between 1 and {_MAX_PAGES}")
    return value


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _check_keys(config: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(
            f"Unknown setting(s) for this source type: {', '.join(unknown)}"
        )


def normalize_source_config(
    source_type: SourceType, config: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate and normalize a source's config for its type.

    Args:
        source_type: The connector that will read it
        config: The admin's settings, possibly None

    Returns:
        The normalized config to store

    Raises:
        ValueError: With a message naming the offending setting
    """
    config = dict(config or {})

    if source_type == SourceType.REMOTIVE:
        _check_keys(config, {"search", "category"})
        return _drop_none(
            {"search": _text(config, "search"), "category": _text(config, "category")}
        )

    if source_type == SourceType.ARBEITNOW:
        _check_keys(config, {"search", "max_pages"})
        return _drop_none(
            {"search": _text(config, "search"), "max_pages": _pages(config)}
        )

    if source_type == SourceType.REMOTEOK:
        _check_keys(config, {"tag"})
        return _drop_none({"tag": _text(config, "tag")})

    if source_type == SourceType.ADZUNA:
        _check_keys(config, {"country", "what", "where", "max_pages"})
        country = _text(config, "country", required=True)
        assert country is not None
        country = country.lower()
        if len(country) != 2 or not country.isalpha():
            raise ValueError("'country' must be a two-letter code, e.g. gb or us")
        return _drop_none(
            {
                "country": country,
                "what": _text(config, "what"),
                "where": _text(config, "where"),
                "max_pages": _pages(config),
            }
        )

    if source_type == SourceType.RSS_FEED:
        _check_keys(config, {"url", "company"})
        return _drop_none(
            {"url": _feed_url(config), "company": _text(config, "company")}
        )

    if source_type == SourceType.JSON_FEED:
        _check_keys(config, {"url", "items_path", "field_map"})
        field_map = config.get("field_map")
        if not isinstance(field_map, dict) or not field_map:
            raise ValueError("'field_map' is required and must map fields to paths")
        _check_keys(field_map, JSON_FIELD_MAP_KEYS)
        missing = sorted(JSON_FIELD_MAP_REQUIRED - set(field_map))
        if missing:
            raise ValueError(f"'field_map' must name: {', '.join(missing)}")
        normalized_map = {}
        for key, path in field_map.items():
            if not isinstance(path, str) or not path.strip():
                raise ValueError(f"'field_map.{key}' must be a dotted path")
            normalized_map[key] = path.strip()
        return _drop_none(
            {
                "url": _feed_url(config),
                "items_path": _text(config, "items_path"),
                "field_map": normalized_map,
            }
        )

    raise ValueError(f"Unsupported source type: {source_type}")  # pragma: no cover

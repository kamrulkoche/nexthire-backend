"""Unit tests for job-side domain helpers: config rules, fingerprint, text, enums."""

import pytest

from src.modules.collection.infrastructure.external.connectors.common import (
    build_job,
    parse_datetime,
    parse_int,
    parse_tags,
)
from src.modules.job.domain.enums.employment_type import EmploymentType
from src.modules.job.domain.services.fingerprint import job_fingerprint
from src.modules.job_source.domain.enums.source_type import SourceType
from src.modules.job_source.domain.services.source_config import normalize_source_config
from src.shared.domain.text import clip, strip_html


@pytest.mark.unit
class TestSourceConfig:
    def test_blank_values_are_dropped(self):
        assert normalize_source_config(
            SourceType.REMOTIVE, {"search": "  ", "category": "dev"}
        ) == {"category": "dev"}

    def test_unknown_keys_are_refused(self):
        with pytest.raises(ValueError, match="Unknown setting"):
            normalize_source_config(SourceType.REMOTEOK, {"tags": "python"})

    def test_feed_urls_must_be_http_without_credentials(self):
        with pytest.raises(ValueError):
            normalize_source_config(SourceType.RSS_FEED, {"url": "file:///etc/passwd"})
        with pytest.raises(ValueError, match="credentials"):
            normalize_source_config(
                SourceType.RSS_FEED, {"url": "https://u:p@x.example/f"}
            )

    def test_max_pages_is_bounded(self):
        with pytest.raises(ValueError):
            normalize_source_config(SourceType.ARBEITNOW, {"max_pages": 50})
        with pytest.raises(ValueError):
            normalize_source_config(SourceType.ARBEITNOW, {"max_pages": True})


@pytest.mark.unit
class TestFingerprint:
    def test_same_role_across_sources_collides(self):
        a = job_fingerprint(
            "Senior Python Engineer (Remote)", "Acme, Inc.", "Berlin, Germany"
        )
        b = job_fingerprint("senior python engineer", "ACME", "Berlin")
        assert a == b

    def test_different_roles_differ(self):
        assert job_fingerprint("Python Engineer", "Acme", None) != job_fingerprint(
            "Java Engineer", "Acme", None
        )


@pytest.mark.unit
class TestText:
    def test_strip_html_keeps_structure_drops_scripts(self):
        html = "<h2>About</h2><p>We&amp;you</p><ul><li>One</li><li>Two</li></ul><script>evil()</script>"
        text = strip_html(html)
        assert "evil" not in text
        assert "We&you" in text
        assert "• One" in text and "• Two" in text

    def test_clip(self):
        assert clip("  a   b  ", 10) == "a b"
        assert clip("", 10) is None
        assert clip("abcdefghij", 5) == "abcd…"


@pytest.mark.unit
class TestParsing:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Full-Time", EmploymentType.FULL_TIME),
            ("permanent", EmploymentType.FULL_TIME),
            ("freelance", EmploymentType.CONTRACT),
            ("gig", EmploymentType.OTHER),
            ("", None),
            (None, None),
        ],
    )
    def test_employment_type_aliases(self, raw, expected):
        assert EmploymentType.from_source(raw) == expected

    def test_dates_in_every_shape_become_aware_utc(self):
        for raw in (
            "2026-10-01T10:00:00Z",
            1759312800,
            "1759312800",
            "Wed, 01 Oct 2026 10:00:00 GMT",
        ):
            parsed = parse_datetime(raw)
            assert parsed is not None and parsed.tzinfo is not None, raw
        assert parse_datetime("not a date") is None

    def test_future_dates_are_clamped_to_now(self):
        parsed = parse_datetime("2099-01-01T00:00:00Z")
        assert parsed is not None and parsed.year < 2099

    def test_ints_and_tags(self):
        assert parse_int("85,000") == 85000
        assert parse_int(-5) is None
        assert parse_int(True) is None
        assert parse_tags("python, Python ,go") == ("python", "go")

    def test_build_job_requires_the_essentials_and_an_http_url(self):
        assert (
            build_job(
                external_id="1", title="T", company="C", url="javascript:alert(1)"
            )
            is None
        )
        assert (
            build_job(external_id="1", title="T", company="", url="https://x") is None
        )
        job = build_job(
            external_id=1,
            title="T",
            company="C",
            url="https://x",
            salary_min=200,
            salary_max=100,
        )
        assert job is not None
        assert (job.salary_min, job.salary_max) == (100, 200)

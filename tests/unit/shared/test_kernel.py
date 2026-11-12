"""Unit tests for the ported shared kernel: pagination, rate limiting, envelope."""

import pytest

from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
)
from src.shared.infrastructure.middleware.response_wrapper_middleware import (
    _splice_envelope,
)
from src.shared.infrastructure.security.rate_limiter import RateLimiter


@pytest.mark.unit
class TestPagination:
    def test_offset_is_zero_based(self):
        assert ListQueryParams(page=3, page_size=10).offset == 20

    def test_blank_search_means_no_filter(self):
        assert ListQueryParams(search="   ").normalized_search is None

    @pytest.mark.parametrize(
        ("total", "pages"), [(0, 0), (1, 1), (12, 1), (13, 2), (24, 2), (25, 3)]
    )
    def test_total_pages_is_a_ceiling(self, total: int, pages: int):
        built = PaginatedResponseSchema.build([], total, ListQueryParams(page_size=12))
        assert built.total_pages == pages


@pytest.mark.unit
class TestRateLimiter:
    def test_allows_up_to_the_limit_then_refuses(self):
        limiter = RateLimiter(limit=2, window_seconds=60)
        assert limiter.check("k")[0]
        assert limiter.check("k")[0]
        allowed, retry_after = limiter.check("k")
        assert not allowed and retry_after > 0

    def test_keys_are_independent_and_reset_forgets(self):
        limiter = RateLimiter(limit=1, window_seconds=60)
        limiter.check("a")
        assert limiter.check("b")[0]
        limiter.reset("a")
        assert limiter.check("a")[0]

    def test_disabled_limiter_allows_everything(self):
        limiter = RateLimiter(limit=1, window_seconds=60, enabled=lambda: False)
        assert all(limiter.check("k")[0] for _ in range(10))

    def test_auth_limit_switch_is_ignored_outside_dev_and_test(self):
        from src.shared.utils.config import Settings

        def active(environment):
            return Settings(
                environment=environment, auth_rate_limit_enabled=False
            ).auth_rate_limit_active

        assert not active("dev")
        assert not active("test")
        assert active("prod")
        assert active("staging")


@pytest.mark.unit
def test_envelope_is_spliced_byte_for_byte():
    assert (
        _splice_envelope(b'{"x":1}', 201)
        == b'{"status":201,"success":true,"data":{"x":1}}'
    )

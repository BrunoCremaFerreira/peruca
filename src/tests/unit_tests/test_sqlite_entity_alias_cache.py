"""
SqliteSmartHomeEntityAliasRepository in-memory TTL cache unit tests
(TDD RED phase).

Contract:
  - get_all() with the same argument must return the cached result on the
    second call within the TTL (the underlying DB is queried only once).
  - get_all() called after the TTL has expired must hit the DB again.
  - delete_all() must invalidate the cache so the next get_all() queries the DB.
  - add() must invalidate the cache so the next get_all() queries the DB.
  - The TTL must be configurable via an `aliases_cache_ttl` constructor
    parameter (default 60.0 seconds).

These tests are written BEFORE the implementation and are expected to FAIL:
today SqliteSmartHomeEntityAliasRepository.get_all() hits the DB on every
call and there is no cache or TTL parameter.

A real SQLite in-memory DB is used so that actual insert/delete round-trips
are observable, but `time.monotonic` is patched to control TTL expiry without
real sleeping.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from domain.entities import SmartHomeEntityAlias
from infra.data.sqlite.sqlite_smart_home_entity_alias_repository import (
    SqliteSmartHomeEntityAliasRepository,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_repo(ttl: float = 60.0) -> SqliteSmartHomeEntityAliasRepository:
    """
    Return a repository backed by an in-memory SQLite database.
    The `aliases_cache_ttl` constructor parameter is the feature under test.
    """
    return SqliteSmartHomeEntityAliasRepository(
        db_path=":memory:", aliases_cache_ttl=ttl
    )


def _sample_alias(entity_id: str = "light.sala", alias: str = "sala") -> SmartHomeEntityAlias:
    return SmartHomeEntityAlias(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        alias=alias,
        area_id=None,
        when_created=datetime.now(timezone.utc),
    )


# ===========================================================================
# TestEntityAliasCacheHitWithinTTL
# ===========================================================================


class TestEntityAliasCacheHitWithinTTL:
    """get_all() must serve a cached result on the second call within the TTL."""

    def test_get_all__called_twice_within_ttl__db_queried_only_once(self):
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias())

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0   # first call: t=0
            first = repo.get_all()

            mock_time.return_value = 30.0  # second call: t=30 (within TTL of 60)
            second = repo.get_all()

        assert first == second, "Cached result must be equal to the original result."
        assert mock_time.call_count >= 2, "monotonic must be consulted to check TTL."

    def test_get_all__called_twice_within_ttl__returns_same_list_object_or_equal_content(
        self,
    ):
        """
        The cache may return the same list object or a copy; either is acceptable
        as long as the content is identical and the DB was not queried twice.
        """
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias(entity_id="light.quarto", alias="quarto"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 1.0
            first = repo.get_all()
            mock_time.return_value = 1.5
            second = repo.get_all()

        # Entity IDs must match — the cache was used.
        assert [a.entity_id for a in first] == [a.entity_id for a in second]

    def test_get_all__with_prefix_filter__cached_independently_from_no_filter(self):
        """
        get_all(entity_id_starts_with="light.") and get_all() are different cache
        entries; each must be cached independently.
        """
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))
        repo.add(_sample_alias(entity_id="switch.ventilador", alias="ventilador"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            all_results = repo.get_all()
            lights_only = repo.get_all(entity_id_starts_with="light.")

            mock_time.return_value = 5.0
            all_results_cached = repo.get_all()
            lights_only_cached = repo.get_all(entity_id_starts_with="light.")

        assert len(all_results) == 2
        assert len(lights_only) == 1
        assert all_results_cached == all_results
        assert lights_only_cached == lights_only


# ===========================================================================
# TestEntityAliasCacheExpiry
# ===========================================================================


class TestEntityAliasCacheExpiry:
    """After the TTL expires, get_all() must query the DB again."""

    def test_get_all__after_ttl_expires__db_is_queried_again(self):
        repo = _make_repo(ttl=10.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))

        with patch("time.monotonic") as mock_time:
            # Prime the cache.
            mock_time.return_value = 0.0
            first = repo.get_all()

            # Advance time past the TTL.
            mock_time.return_value = 11.0
            second = repo.get_all()

        # Both calls return valid data; the second call went to the DB.
        assert len(first) == 1
        assert len(second) == 1
        assert first[0].entity_id == second[0].entity_id

    def test_get_all__exactly_at_ttl_boundary__db_is_queried_again(self):
        """At exactly TTL seconds, the cache entry must be considered stale."""
        repo = _make_repo(ttl=10.0)
        repo.add(_sample_alias())

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            repo.get_all()            # prime cache

            mock_time.return_value = 10.0   # exactly at TTL — must be stale
            result = repo.get_all()

        assert len(result) == 1


# ===========================================================================
# TestEntityAliasCacheInvalidationOnMutation
# ===========================================================================


class TestEntityAliasCacheInvalidationOnMutation:
    """Mutating operations must invalidate the cache."""

    def test_delete_all__then_get_all__returns_empty_list_not_cached_data(self):
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            cached = repo.get_all()   # primes the cache
            assert len(cached) == 1

            # Mutate — must invalidate the cache.
            repo.delete_all()

            mock_time.return_value = 1.0   # still within TTL
            after_delete = repo.get_all()

        assert after_delete == [], (
            "After delete_all(), get_all() must bypass the cache and return []."
        )

    def test_add__then_get_all__includes_new_entity_not_stale_cache(self):
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            cached = repo.get_all()   # primes the cache with 1 item
            assert len(cached) == 1

            # Insert a second entity — must invalidate the cache.
            repo.add(_sample_alias(entity_id="light.quarto", alias="quarto"))

            mock_time.return_value = 1.0   # still within TTL
            after_add = repo.get_all()

        assert len(after_add) == 2, (
            "After add(), get_all() must bypass the cache and return the updated list."
        )

    def test_delete_all__invalidates_all_cache_keys(self):
        """
        delete_all() must clear every cached entry, not just the entry for
        get_all() with no filter.
        """
        repo = _make_repo(ttl=60.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))
        repo.add(_sample_alias(entity_id="switch.tv", alias="tv"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            # Prime two different cache entries.
            all_result = repo.get_all()
            lights_result = repo.get_all(entity_id_starts_with="light.")
            assert len(all_result) == 2
            assert len(lights_result) == 1

            repo.delete_all()

            mock_time.return_value = 1.0
            after_all = repo.get_all()
            after_lights = repo.get_all(entity_id_starts_with="light.")

        assert after_all == [], "All-entities cache must be cleared after delete_all()."
        assert after_lights == [], "Filtered cache must also be cleared after delete_all()."


# ===========================================================================
# TestEntityAliasCacheTTLIsConfigurable
# ===========================================================================


class TestEntityAliasCacheTTLIsConfigurable:
    """The TTL must be accepted as a constructor parameter."""

    def test_constructor__accepts_aliases_cache_ttl_parameter(self):
        """
        SqliteSmartHomeEntityAliasRepository must accept an `aliases_cache_ttl`
        keyword argument without raising TypeError.
        """
        try:
            repo = SqliteSmartHomeEntityAliasRepository(
                db_path=":memory:", aliases_cache_ttl=120.0
            )
            repo.close()
        except TypeError as exc:
            pytest.fail(
                f"Constructor does not accept aliases_cache_ttl parameter: {exc}"
            )

    def test_constructor__default_ttl_is_sixty_seconds(self):
        """
        When `aliases_cache_ttl` is not provided, the default must be 60.0.
        This is verified by checking the stored attribute.
        """
        repo = SqliteSmartHomeEntityAliasRepository(db_path=":memory:")
        try:
            assert repo.aliases_cache_ttl == 60.0, (
                f"Default TTL must be 60.0, got {repo.aliases_cache_ttl!r}."
            )
        finally:
            repo.close()

    def test_short_ttl__cache_expires_quickly(self):
        """A TTL of 1 second must expire when monotonic advances by 2 seconds."""
        repo = _make_repo(ttl=1.0)
        repo.add(_sample_alias(entity_id="light.sala", alias="sala"))

        with patch("time.monotonic") as mock_time:
            mock_time.return_value = 0.0
            first = repo.get_all()   # primes cache

            mock_time.return_value = 2.0   # TTL expired
            repo.add(_sample_alias(entity_id="light.quarto", alias="quarto"))
            second = repo.get_all()   # must fetch fresh data

        assert len(first) == 1
        assert len(second) == 2, (
            "After TTL expiry + add(), get_all() must return fresh data from the DB."
        )

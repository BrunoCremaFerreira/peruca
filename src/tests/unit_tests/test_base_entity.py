"""
BaseEntity.when_created tests (TDD) — §10.1 of the user-timezone plan.

``when_created: datetime = datetime.now(timezone.utc)`` is a dataclass default
evaluated ONCE at import time, so every entity built without an explicit
``when_created`` shares the process-start timestamp. These tests freeze the
intended contract: the default is computed per instance (``default_factory``),
timezone-aware in UTC, and never overrides an explicit value.

Determinism without sleeps: the timestamps are captured around the construction
(``t0 <= entity.when_created <= t1``) instead of compared to each other, so the
assertion holds no matter how coarse the clock is.
"""

from datetime import datetime, timedelta, timezone

from domain.entities import BaseEntity, User


class TestBaseEntityWhenCreated:
    def test_two_instances__have_distinct_when_created(self):
        # Arrange
        t0 = datetime.now(timezone.utc)
        # Act
        first = BaseEntity()
        second = BaseEntity()
        t1 = datetime.now(timezone.utc)
        # Assert — both timestamps must be born inside the construction window,
        # which the import-time default (far in the past) can never satisfy.
        assert t0 <= first.when_created <= t1
        assert t0 <= second.when_created <= t1
        assert first.when_created <= second.when_created

    def test_default__is_timezone_aware_utc(self):
        # Act
        entity = BaseEntity()
        # Assert
        assert entity.when_created.tzinfo is not None
        assert entity.when_created.utcoffset() == timedelta(0)

    def test_explicit_value__not_overridden(self):
        # Arrange
        explicit = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        # Act
        entity = BaseEntity(id="abc", when_created=explicit)
        # Assert
        assert entity.when_created == explicit

    def test_subclass__also_gets_a_fresh_timestamp(self):
        # Arrange
        t0 = datetime.now(timezone.utc)
        # Act
        user = User(id="u1", external_id="u1", name="Alice")
        t1 = datetime.now(timezone.utc)
        # Assert
        assert t0 <= user.when_created <= t1

    def test_other_timestamps__default_to_none(self):
        # Act
        entity = BaseEntity()
        # Assert
        assert entity.when_updated is None
        assert entity.when_deleted is None

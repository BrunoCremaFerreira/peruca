"""
domain/services/clock.py tests (TDD) — §10.2 of the user-timezone plan.

Pure stdlib (``zoneinfo``) functions, deterministic by parameter injection
(``now_utc``) exactly like ``date_resolver`` — no freezegun, no datetime patch.

Contract exercised here:

    now_for_timezone(tz: str, *, now_utc: datetime | None = None) -> datetime
    to_local(dt_utc: datetime, tz: str) -> datetime
    format_local(dt_utc: datetime, tz: str, fmt: str) -> str
    local_date_for_user(tz: str, *, now_utc: datetime | None = None) -> date
    max_civil_date_on_earth(*, now_utc: datetime | None = None) -> date

Invariants: the returned datetimes are timezone-aware; an invalid/empty tz raises
the domain ``ValidationError`` (a ``ZoneInfoNotFoundError`` must NEVER leak); a
naive ``now_utc`` is rejected (fail-fast); a naive ``dt_utc`` (what SQLite hands
back) is assumed to be UTC.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from domain.exceptions import ValidationError
from domain.services.clock import (
    format_local,
    local_date_for_user,
    max_civil_date_on_earth,
    now_for_timezone,
    to_local,
)
from domain.services.date_resolver import resolve_date_token, resolve_period


SAO_PAULO = "America/Sao_Paulo"
LISBON = "Europe/Lisbon"


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class TestNowForTimezone:
    def test_valid_iana__returns_aware_datetime(self):
        # Act
        result = now_for_timezone(SAO_PAULO)
        # Assert
        assert result.tzinfo is not None
        assert result.utcoffset() is not None

    def test_sao_paulo__offset_minus_three(self):
        # Arrange
        now_utc = _utc(2026, 7, 10, 12, 0)
        # Act
        result = now_for_timezone(SAO_PAULO, now_utc=now_utc)
        # Assert
        assert result.utcoffset() == timedelta(hours=-3)
        assert (result.year, result.month, result.day) == (2026, 7, 10)
        assert (result.hour, result.minute) == (9, 0)

    def test_lisbon_summer__offset_plus_one(self):
        # Arrange — July: WEST (DST active).
        now_utc = _utc(2026, 7, 10, 12, 0)
        # Act
        result = now_for_timezone(LISBON, now_utc=now_utc)
        # Assert
        assert result.utcoffset() == timedelta(hours=1)
        assert result.hour == 13

    def test_lisbon_winter__offset_zero(self):
        # Arrange — January: WET (no DST).
        now_utc = _utc(2026, 1, 10, 12, 0)
        # Act
        result = now_for_timezone(LISBON, now_utc=now_utc)
        # Assert
        assert result.utcoffset() == timedelta(0)
        assert result.hour == 12

    def test_no_now_utc__uses_the_current_instant(self):
        # Arrange
        before = datetime.now(timezone.utc)
        # Act
        result = now_for_timezone(SAO_PAULO)
        after = datetime.now(timezone.utc)
        # Assert
        assert before <= result.astimezone(timezone.utc) <= after

    def test_invalid_tz__raises_validation_error(self):
        # Act / Assert — the LLM's plausible hallucination must not blow up with
        # a zoneinfo error; the domain speaks ValidationError.
        with pytest.raises(ValidationError) as exc:
            now_for_timezone("America/Sao_Paolo")
        assert not isinstance(exc.value, ZoneInfoNotFoundError)

    def test_empty_tz__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            now_for_timezone("")

    def test_naive_now_utc__raises_validation_error(self):
        # Act / Assert — fail-fast: a naive "now" has no known instant.
        with pytest.raises(ValidationError):
            now_for_timezone(SAO_PAULO, now_utc=datetime(2026, 7, 10, 12, 0))


class TestToLocal:
    def test_utc_datetime__converted_to_sao_paulo(self):
        # Arrange — 01:00Z is still the PREVIOUS civil day in São Paulo.
        dt_utc = _utc(2026, 7, 10, 1, 0)
        # Act
        local = to_local(dt_utc, SAO_PAULO)
        # Assert
        assert local.utcoffset() == timedelta(hours=-3)
        assert local.date() == date(2026, 7, 9)
        assert (local.hour, local.minute) == (22, 0)

    def test_naive_input__assumed_utc(self):
        # Arrange — SQLite hands datetimes back without tzinfo.
        naive = datetime(2026, 7, 10, 1, 0)
        # Act
        local = to_local(naive, SAO_PAULO)
        # Assert
        assert local.date() == date(2026, 7, 9)
        assert local.hour == 22
        assert local.tzinfo is not None

    def test_conversion_preserves_instant(self):
        # Arrange
        dt_utc = _utc(2026, 7, 10, 15, 42, 7)
        # Act
        local = to_local(dt_utc, LISBON)
        # Assert
        assert local.astimezone(timezone.utc) == dt_utc

    def test_invalid_tz__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            to_local(_utc(2026, 7, 10, 1, 0), "Mars/Olympus_Mons")

    def test_empty_tz__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            to_local(_utc(2026, 7, 10, 1, 0), "")


class TestFormatLocal:
    def test_utc_datetime__formatted_in_local_timezone(self):
        # Arrange
        dt_utc = _utc(2026, 7, 10, 1, 0)
        # Act
        result = format_local(dt_utc, SAO_PAULO, "%d/%m/%Y %H:%M")
        # Assert
        assert result == "09/07/2026 22:00"

    def test_naive_input__assumed_utc(self):
        # Arrange
        naive = datetime(2026, 7, 10, 1, 0)
        # Act
        result = format_local(naive, SAO_PAULO, "%H:%M")
        # Assert
        assert result == "22:00"

    def test_invalid_tz__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            format_local(_utc(2026, 7, 10, 1, 0), "Nowhere/Nothing", "%H:%M")


class TestLocalDateForUser:
    def test_midnight_edge__local_date_is_previous_day(self):
        # Arrange — 02:30Z is 23:30 of the previous day in São Paulo.
        now_utc = _utc(2026, 7, 10, 2, 30)
        # Act
        result = local_date_for_user(SAO_PAULO, now_utc=now_utc)
        # Assert
        assert result == date(2026, 7, 9)

    def test_midnight_edge__same_instant_is_the_next_day_in_lisbon(self):
        # Arrange — the same instant, a different user timezone.
        now_utc = _utc(2026, 7, 10, 2, 30)
        # Act
        result = local_date_for_user(LISBON, now_utc=now_utc)
        # Assert
        assert result == date(2026, 7, 10)

    def test_no_now_utc__uses_the_current_instant(self):
        # Arrange
        before = datetime.now(timezone.utc).astimezone(ZoneInfo(SAO_PAULO)).date()
        # Act
        result = local_date_for_user(SAO_PAULO)
        after = datetime.now(timezone.utc).astimezone(ZoneInfo(SAO_PAULO)).date()
        # Assert — tolerant of a midnight turn between the captures.
        assert result in (before, after)

    def test_invalid_tz__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            local_date_for_user("America/Sao_Paolo")

    def test_naive_now_utc__raises_validation_error(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            local_date_for_user(SAO_PAULO, now_utc=datetime(2026, 7, 10, 2, 30))


class TestMaxCivilDateOnEarth:
    """
    A civil date (performed_at / occurred_at / birth_date) carries NO timezone,
    so "is it in the future?" is only answerable against the greatest local date
    that exists anywhere on Earth — UTC+14 (Kiritimati), i.e. ``utc_today + 1``.
    Comparing it to the SERVER's ``date.today()`` makes an arbitrary timezone the
    authority over a timezone-less type, and rejects a date that is simply
    "today" for a user living ahead of the server.
    """

    def test_injected_now_utc__is_the_utc_date_plus_one_day(self):
        # Arrange
        now_utc = _utc(2026, 7, 10, 23, 59)
        # Act / Assert
        assert max_civil_date_on_earth(now_utc=now_utc) == date(2026, 7, 11)

    def test_injected_now_utc__start_of_day__still_plus_one_day(self):
        # Arrange — the bound depends on the DATE, never on the time of day.
        now_utc = _utc(2026, 7, 10, 0, 1)
        # Act / Assert
        assert max_civil_date_on_earth(now_utc=now_utc) == date(2026, 7, 11)

    def test_injected_now_utc__crosses_month_and_year_boundaries(self):
        assert max_civil_date_on_earth(now_utc=_utc(2026, 12, 31, 12, 0)) == date(
            2027, 1, 1
        )

    def test_no_now_utc__uses_the_current_instant(self):
        # Arrange
        before = datetime.now(timezone.utc).date()
        # Act
        result = max_civil_date_on_earth()
        after = datetime.now(timezone.utc).date()
        # Assert — tolerant of a UTC midnight turn between the captures.
        assert result in (
            before + timedelta(days=1),
            after + timedelta(days=1),
        )

    def test_naive_now_utc__raises_validation_error(self):
        # Act / Assert — fail-fast, same contract as the other clock functions.
        with pytest.raises(ValidationError):
            max_civil_date_on_earth(now_utc=datetime(2026, 7, 10, 23, 59))


class TestLocalDateBridgesDateResolver:
    """
    The bridge that fixes the bug: date_resolver already takes its ``reference``
    by parameter, so feeding it the user's LOCAL date (instead of the server's
    ``date.today()``) is all it takes for "today"/"this_week" to mean what the
    user means.
    """

    def test_today_token_with_local_reference(self):
        # Arrange — server UTC date is the 10th; the user's local date is the 9th.
        now_utc = _utc(2026, 7, 10, 2, 30)
        reference = local_date_for_user(SAO_PAULO, now_utc=now_utc)
        # Act
        resolved = resolve_date_token("today", reference)
        # Assert
        assert resolved == date(2026, 7, 9)
        assert resolved != now_utc.date()

    def test_yesterday_token_with_local_reference(self):
        # Arrange
        now_utc = _utc(2026, 7, 10, 2, 30)
        reference = local_date_for_user(SAO_PAULO, now_utc=now_utc)
        # Act / Assert
        assert resolve_date_token("yesterday", reference) == date(2026, 7, 8)

    def test_this_week_period__week_turn_uses_the_local_date(self):
        # Arrange — 2026-07-13 02:30Z is a Monday in UTC but still Sunday
        # 2026-07-12 in São Paulo, so "this week" is the PREVIOUS ISO week.
        now_utc = _utc(2026, 7, 13, 2, 30)
        reference = local_date_for_user(SAO_PAULO, now_utc=now_utc)
        # Act
        start, end = resolve_period("this_week", reference)
        # Assert
        assert reference == date(2026, 7, 12)
        assert (start, end) == (date(2026, 7, 6), date(2026, 7, 12))
        # The server's UTC "today" would have collapsed the week to a single day.
        assert resolve_period("this_week", now_utc.date()) == (
            date(2026, 7, 13),
            date(2026, 7, 13),
        )

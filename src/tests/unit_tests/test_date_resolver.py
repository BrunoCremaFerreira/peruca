"""
date_resolver unit tests (TDD — written before implementation).

The LLM never does calendar arithmetic (§9.2 of the plan). It emits closed
tokens (date_token / period) or transcribes a dictated date (date_value); this
module resolves them deterministically. References are fixed to force month/year
borrows and leap-year edges.

API under test:
    resolve_date_token(token, reference) -> Optional[date]
    parse_explicit_date(text, reference) -> Optional[date]
    resolve_period(token, reference) -> Optional[tuple[date, date]]
"""

from datetime import date

import pytest

from domain.services.date_resolver import (
    parse_explicit_date,
    resolve_date_token,
    resolve_period,
)


class TestResolveDateToken:
    def test_today__returns_reference(self):
        ref = date(2026, 7, 5)
        assert resolve_date_token("today", ref) == date(2026, 7, 5)

    def test_yesterday__returns_reference_minus_one(self):
        ref = date(2026, 7, 5)
        assert resolve_date_token("yesterday", ref) == date(2026, 7, 4)

    def test_day_before_yesterday__returns_reference_minus_two(self):
        ref = date(2026, 7, 5)
        assert resolve_date_token("day_before_yesterday", ref) == date(2026, 7, 3)

    def test_yesterday_on_first_of_year__borrows_year(self):
        ref = date(2026, 1, 1)
        assert resolve_date_token("yesterday", ref) == date(2025, 12, 31)

    def test_yesterday_on_first_of_march_leap_year__returns_feb_29(self):
        ref = date(2024, 3, 1)
        assert resolve_date_token("yesterday", ref) == date(2024, 2, 29)

    def test_empty_token__returns_none(self):
        assert resolve_date_token("", date(2026, 7, 5)) is None

    def test_unknown_token__returns_none(self):
        assert resolve_date_token("last_fortnight", date(2026, 7, 5)) is None


class TestParseExplicitDate:
    def test_full_ddmmyyyy(self):
        assert parse_explicit_date("21/07/2026", date(2026, 7, 5)) == date(2026, 7, 21)

    def test_iso_yyyymmdd(self):
        assert parse_explicit_date("2026-07-21", date(2026, 7, 5)) == date(2026, 7, 21)

    def test_partial_llm_form_month_day_infers_year(self):
        # "--07-21" with a July reference -> current year (not future).
        assert parse_explicit_date("--07-21", date(2026, 8, 1)) == date(2026, 7, 21)

    def test_ddmm_without_year_defaults_to_reference_year(self):
        assert parse_explicit_date("12/06", date(2026, 7, 5)) == date(2026, 6, 12)

    def test_ddmm_that_would_be_future_rolls_back_one_year(self):
        # "21/12" seen on 2026-07-05 must be last December, not this one.
        assert parse_explicit_date("21/12", date(2026, 7, 5)) == date(2025, 12, 21)

    def test_two_digit_year(self):
        assert parse_explicit_date("21/07/26", date(2026, 7, 5)) == date(2026, 7, 21)

    def test_invalid_calendar_date_returns_none(self):
        assert parse_explicit_date("31/02/2026", date(2026, 7, 5)) is None

    def test_non_date_text_returns_none(self):
        assert parse_explicit_date("amanhã", date(2026, 7, 5)) is None

    def test_empty_returns_none(self):
        assert parse_explicit_date("", date(2026, 7, 5)) is None


class TestResolvePeriod:
    def test_today(self):
        ref = date(2026, 7, 5)
        assert resolve_period("today", ref) == (date(2026, 7, 5), date(2026, 7, 5))

    def test_yesterday(self):
        ref = date(2026, 7, 5)
        assert resolve_period("yesterday", ref) == (date(2026, 7, 4), date(2026, 7, 4))

    def test_this_week_starts_monday_and_ends_reference(self):
        # 2026-07-05 is a Sunday; its week starts Monday 2026-06-29.
        ref = date(2026, 7, 5)
        assert resolve_period("this_week", ref) == (date(2026, 6, 29), date(2026, 7, 5))

    def test_last_week_crosses_month(self):
        ref = date(2026, 7, 5)  # Sunday
        assert resolve_period("last_week", ref) == (date(2026, 6, 22), date(2026, 6, 28))

    def test_this_month_caps_end_at_reference(self):
        ref = date(2026, 7, 5)
        assert resolve_period("this_month", ref) == (date(2026, 7, 1), date(2026, 7, 5))

    def test_last_month(self):
        ref = date(2026, 7, 5)
        assert resolve_period("last_month", ref) == (date(2026, 6, 1), date(2026, 6, 30))

    def test_last_month_on_january_borrows_year(self):
        ref = date(2026, 1, 15)
        assert resolve_period("last_month", ref) == (date(2025, 12, 1), date(2025, 12, 31))

    def test_last_month_february_leap_year(self):
        ref = date(2024, 3, 10)
        assert resolve_period("last_month", ref) == (date(2024, 2, 1), date(2024, 2, 29))

    def test_last_month_february_non_leap_year(self):
        ref = date(2026, 3, 10)
        assert resolve_period("last_month", ref) == (date(2026, 2, 1), date(2026, 2, 28))

    def test_this_year_caps_end_at_reference(self):
        ref = date(2026, 7, 5)
        assert resolve_period("this_year", ref) == (date(2026, 1, 1), date(2026, 7, 5))

    def test_last_year(self):
        ref = date(2026, 7, 5)
        assert resolve_period("last_year", ref) == (date(2025, 1, 1), date(2025, 12, 31))

    def test_unknown_token_returns_none(self):
        assert resolve_period("last_fortnight", date(2026, 7, 5)) is None

    def test_empty_token_returns_none(self):
        assert resolve_period("", date(2026, 7, 5)) is None

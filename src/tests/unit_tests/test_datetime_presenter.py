"""
Datetime presenter unit tests (TDD RED — plan §7 / §10.6).

`domain/services/clock.py` is deliberately locale-free (it only knows instants and
strftime formats). The pt-BR wording a prompt shows the user — above all the
weekday spelled out, which the models systematically get wrong when they have to
derive it from a date — lives in the application layer:

    application/appservices/datetime_presenter.py

        WEEKDAYS_PT_BR: tuple[str, ...]   # index == date.weekday() (Mon..Sun)

        def format_weekday_pt_br(value: date | datetime) -> str
            "quinta-feira"

        def format_current_datetime(tz: str, *, now_utc: datetime | None = None) -> str
            "sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)"

Determinism is by parameter injection (`now_utc`), the `date_resolver`/`clock`
pattern — no freezegun, no patching of datetime. An invalid/empty timezone must
surface the domain ValidationError raised by clock (fail-fast: never pretend a
default timezone here — the single source of truth is LlmAppService).
"""

from datetime import date, datetime, timezone

import pytest

from domain.exceptions import ValidationError

from application.appservices.datetime_presenter import (
    format_current_datetime,
    format_weekday_pt_br,
)


def _utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestFormatWeekdayPtBr:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (date(2026, 7, 6), "segunda-feira"),
            (date(2026, 7, 7), "terça-feira"),
            (date(2026, 7, 8), "quarta-feira"),
            (date(2026, 7, 9), "quinta-feira"),
            (date(2026, 7, 10), "sexta-feira"),
            (date(2026, 7, 11), "sábado"),
            (date(2026, 7, 12), "domingo"),
        ],
    )
    def test_every_weekday__spelled_out_in_pt_br(self, value, expected):
        assert format_weekday_pt_br(value) == expected

    def test_accepts_a_datetime_too(self):
        assert format_weekday_pt_br(_utc(2026, 7, 10, 14, 32)) == "sexta-feira"


class TestFormatCurrentDatetime:
    def test_sao_paulo__weekday_date_time_and_timezone(self):
        rendered = format_current_datetime(
            "America/Sao_Paulo", now_utc=_utc(2026, 7, 10, 14, 32)
        )
        assert rendered == "sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)"

    def test_midnight_edge__renders_the_users_previous_day(self):
        # 02:30Z is still 23:30 of the day before in São Paulo — the whole point
        # of the feature.
        rendered = format_current_datetime(
            "America/Sao_Paulo", now_utc=_utc(2026, 7, 10, 2, 30)
        )
        assert rendered == "quinta-feira, 09/07/2026 23:30 (America/Sao_Paulo)"

    def test_same_instant_other_timezone__different_local_time(self):
        rendered = format_current_datetime(
            "Asia/Tokyo", now_utc=_utc(2026, 7, 10, 14, 32)
        )
        assert rendered == "sexta-feira, 10/07/2026 23:32 (Asia/Tokyo)"

    def test_no_now_utc__uses_the_current_instant(self):
        rendered = format_current_datetime("America/Sao_Paulo")
        assert "(America/Sao_Paulo)" in rendered
        assert "-feira" in rendered or any(
            day in rendered for day in ("sábado", "domingo")
        )

    def test_empty_timezone__raises_validation_error(self):
        # Fail-fast: a graph handed an empty timezone must blow up loudly instead
        # of silently pretending São Paulo.
        with pytest.raises(ValidationError):
            format_current_datetime("", now_utc=_utc(2026, 7, 10, 14, 32))

    def test_invalid_timezone__raises_validation_error(self):
        with pytest.raises(ValidationError):
            format_current_datetime(
                "America/Sao_Paolo", now_utc=_utc(2026, 7, 10, 14, 32)
            )

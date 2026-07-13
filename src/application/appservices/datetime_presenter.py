"""
Presentation of an instant in the user's timezone, spelled out in pt-BR.

``domain/services/clock.py`` is locale-free by design: it knows instants and
strftime formats, not words. The wording a prompt shows the user — above all the
weekday spelled out, which the models systematically get wrong when they have to
derive it from a date — is a presentation concern and lives here, in the
application layer.

Determinism by parameter injection (``now_utc``), the ``date_resolver``/``clock``
pattern. An empty or invalid timezone surfaces the domain ``ValidationError``
raised by the clock: there is no default timezone here, because the single source
of truth for it is ``LlmAppService.chat()``.
"""

from datetime import date, datetime
from typing import Optional, Union

from domain.services.clock import now_for_timezone


# Index == date.weekday() (Monday == 0).
WEEKDAYS_PT_BR: tuple[str, ...] = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def format_weekday_pt_br(value: Union[date, datetime]) -> str:
    """The pt-BR name of the weekday of a date (or of a datetime's date)."""
    return WEEKDAYS_PT_BR[value.weekday()]


def format_current_datetime(tz: str, *, now_utc: Optional[datetime] = None) -> str:
    """
    The current instant in the user's timezone, ready to be injected into a
    prompt: "sexta-feira, 10/07/2026 11:32 (America/Sao_Paulo)".
    """
    local = now_for_timezone(tz, now_utc=now_utc)
    return (
        f"{format_weekday_pt_br(local)}, "
        f"{local.strftime('%d/%m/%Y %H:%M')} ({tz.strip()})"
    )

"""
Deterministic timezone-aware clock helpers.

Same philosophy as ``date_resolver``: pure stdlib functions, no state, and
determinism by parameter injection (``now_utc``) instead of patching
``datetime`` — the caller that needs a frozen instant passes one.

Invariants:
  * an invalid or empty timezone raises the domain ``ValidationError``; a
    ``ZoneInfoNotFoundError`` must never leak out of the domain;
  * a naive ``now_utc`` is rejected (fail-fast: it names no instant);
  * a naive ``dt_utc`` — what SQLite hands back — is assumed to be UTC;
  * the module is locale-free: formatting is delegated to the caller's ``fmt``.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

from domain.exceptions import ValidationError


# ``available_timezones()`` walks the tz database on disk; cache the set once.
_AVAILABLE_TIMEZONES: Optional[frozenset] = None

# The greatest UTC offset in use on Earth (UTC+14, Kiritimati): the local civil
# date there is at most one day ahead of the UTC date.
_MAX_EARTH_DATE_OFFSET = timedelta(days=1)


def available_timezone_names() -> frozenset:
    """Every valid IANA identifier, cached after the first (disk-reading) call."""
    global _AVAILABLE_TIMEZONES
    if _AVAILABLE_TIMEZONES is None:
        _AVAILABLE_TIMEZONES = frozenset(available_timezones())
    return _AVAILABLE_TIMEZONES


def is_valid_timezone(tz: str) -> bool:
    """True when ``tz`` is a known IANA identifier."""
    if not tz or not isinstance(tz, str):
        return False
    return tz.strip() in available_timezone_names()


def now_for_timezone(tz: str, *, now_utc: Optional[datetime] = None) -> datetime:
    """The current instant as an aware datetime in the user's timezone."""
    return _as_utc(now_utc).astimezone(_zone(tz))


def to_local(dt_utc: datetime, tz: str) -> datetime:
    """Convert a UTC datetime (naive values are assumed to be UTC) to ``tz``."""
    if not isinstance(dt_utc, datetime):
        raise ValidationError(["The datetime to convert is not a datetime"])
    zone = _zone(tz)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(zone)


def format_local(dt_utc: datetime, tz: str, fmt: str) -> str:
    """Render a UTC datetime in the user's timezone with a strftime format."""
    return to_local(dt_utc, tz).strftime(fmt)


def local_date_for_user(tz: str, *, now_utc: Optional[datetime] = None) -> date:
    """
    The user's current civil date — the reference ``date_resolver`` needs so that
    "today"/"this_week" mean what the user means, not what the server's timezone
    says.
    """
    return now_for_timezone(tz, now_utc=now_utc).date()


def max_civil_date_on_earth(*, now_utc: Optional[datetime] = None) -> date:
    """
    The greatest civil date that exists anywhere on Earth right now (UTC+14).

    A civil date (performed_at / occurred_at / birth_date) carries no timezone,
    so this is the only correct, timezone-independent upper bound for a "not in
    the future" guard: comparing against the server's local date would make an
    arbitrary timezone the authority over a timezone-less type and would reject a
    legitimate "today" from a user living ahead of the server.
    """
    return _as_utc(now_utc).date() + _MAX_EARTH_DATE_OFFSET


def _zone(tz: str) -> ZoneInfo:
    if not tz or not isinstance(tz, str) or not tz.strip():
        raise ValidationError(["The 'timezone' is empty"])
    name = tz.strip()
    if name not in available_timezone_names():
        raise ValidationError([f"Invalid timezone: {tz}"])
    return ZoneInfo(name)


def _as_utc(now_utc: Optional[datetime]) -> datetime:
    if now_utc is None:
        return datetime.now(timezone.utc)
    if not isinstance(now_utc, datetime):
        raise ValidationError(["The 'now_utc' is not a datetime"])
    if now_utc.tzinfo is None:
        raise ValidationError(["The 'now_utc' must be timezone-aware"])
    return now_utc.astimezone(timezone.utc)

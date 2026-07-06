"""
Deterministic date/period resolution for the vehicle-maintenance domain.

The LLM never performs calendar arithmetic (§9.2 of the plan) — not even
"yesterday", whose month/year borrow is exactly what a small model gets wrong.
It emits closed tokens (``date_token`` / ``period``) or transcribes a dictated
date (``date_value``); this module turns those into concrete dates. Pure stdlib,
no state.
"""

import calendar
import re
from datetime import date, timedelta
from typing import Optional, Tuple


DATE_TOKENS = frozenset({"today", "yesterday", "day_before_yesterday"})

PERIOD_TOKENS = frozenset(
    {
        "today",
        "yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "this_year",
        "last_year",
    }
)

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_PARTIAL_RE = re.compile(r"^--(\d{2})-(\d{2})$")
_DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DDMMYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$")
_DDMM_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def resolve_date_token(token: str, reference: date) -> Optional[date]:
    """today/yesterday/day_before_yesterday -> concrete date; None otherwise."""
    if token == "today":
        return reference
    if token == "yesterday":
        return reference - timedelta(days=1)
    if token == "day_before_yesterday":
        return reference - timedelta(days=2)
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_explicit_date(text: str, reference: date) -> Optional[date]:
    """
    Parse a date the user dictated. Supports ``dd/mm/yyyy``, ``dd/mm/yy``,
    ``dd/mm`` (year inferred from ``reference``), ``yyyy-mm-dd`` and the LLM
    partial form ``--mm-dd``. When the year is inferred and the resulting date
    would be in the future relative to ``reference``, it rolls back one year
    (a maintenance was always performed in the past). Returns None for
    unparseable or impossible dates (e.g. 31/02).
    """
    if not text:
        return None
    text = text.strip()

    m = _ISO_RE.match(text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _DDMMYYYY_RE.match(text)
    if m:
        return _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = _DDMMYY_RE.match(text)
    if m:
        return _safe_date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # Year-inferred forms: dd/mm and --mm-dd.
    m = _DDMM_RE.match(text)
    if m:
        return _infer_year(reference, int(m.group(2)), int(m.group(1)))

    m = _PARTIAL_RE.match(text)
    if m:
        return _infer_year(reference, int(m.group(1)), int(m.group(2)))

    return None


def _infer_year(reference: date, month: int, day: int) -> Optional[date]:
    candidate = _safe_date(reference.year, month, day)
    if candidate is None:
        return None
    if candidate > reference:
        candidate = _safe_date(reference.year - 1, month, day)
    return candidate


def resolve_period(token: str, reference: date) -> Optional[Tuple[date, date]]:
    """
    Closed period token -> (start, end) inclusive, or None for an unknown token.
    ``this_*`` periods cap ``end`` at ``reference`` (never in the future). Weeks
    are ISO (Monday-first).
    """
    if token == "today":
        return (reference, reference)
    if token == "yesterday":
        y = reference - timedelta(days=1)
        return (y, y)
    if token == "this_week":
        monday = reference - timedelta(days=reference.weekday())
        return (monday, reference)
    if token == "last_week":
        this_monday = reference - timedelta(days=reference.weekday())
        return (this_monday - timedelta(days=7), this_monday - timedelta(days=1))
    if token == "this_month":
        return (reference.replace(day=1), reference)
    if token == "last_month":
        first_this_month = reference.replace(day=1)
        last_prev = first_this_month - timedelta(days=1)
        return (last_prev.replace(day=1), last_prev)
    if token == "this_year":
        return (date(reference.year, 1, 1), reference)
    if token == "last_year":
        prev = reference.year - 1
        last_day = calendar.monthrange(prev, 12)[1]
        return (date(prev, 1, 1), date(prev, 12, last_day))
    return None

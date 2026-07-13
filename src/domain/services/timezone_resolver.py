"""
Deterministic resolution of what the user said into an IANA timezone identifier.

Python is the authority, never the LLM: the model may suggest a ``timezone_iana``
(it knows the common ones, but invents plausible-looking identifiers for the rest
— "America/Lisboa"), and it faithfully transcribes the ``location`` the user
spoke. This module decides:

  1. ``timezone_iana`` is used only when it really exists in the tz database;
  2. otherwise the ``location`` is looked up in the curated pt-BR dictionary
     (accent/case-insensitive), with the shared fuzzy matcher as a fallback so a
     typo still resolves;
  3. nothing resolves -> ``None``. The resolver never guesses.

Pure functions, no I/O beyond the (cached) tz database read in ``clock``.
"""

from typing import List, Optional, Tuple

from domain.services.clock import is_valid_timezone
from domain.services.text_matching import find_by_term


# Curated pt-BR aliases -> IANA. What people actually say out loud ("horário de
# brasília", "nova iorque"), not what the tz database calls it. Keeping it small
# and explicit is the point: an unknown place must resolve to None, not to a
# guess.
_CURATED_TIMEZONES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "America/Sao_Paulo",
        (
            "são paulo",
            "sp",
            "brasília",
            "horário de brasília",
            "horario de brasilia",
            "rio de janeiro",
            "belo horizonte",
            "curitiba",
            "porto alegre",
            "salvador",
            "recife",
            "fortaleza",
            "brasil",
        ),
    ),
    ("America/Manaus", ("manaus", "amazonas", "cuiabá", "campo grande", "porto velho")),
    ("America/Rio_Branco", ("rio branco", "acre")),
    ("America/Belem", ("belém",)),
    ("America/Bahia", ("bahia",)),
    ("America/Noronha", ("fernando de noronha", "noronha")),
    ("Europe/Lisbon", ("lisboa", "portugal", "porto")),
    ("Europe/London", ("londres", "inglaterra", "reino unido")),
    ("Europe/Madrid", ("madri", "madrid", "espanha", "barcelona")),
    ("Europe/Paris", ("paris", "frança")),
    ("Europe/Berlin", ("berlim", "alemanha")),
    ("Europe/Rome", ("roma", "itália")),
    ("America/New_York", ("nova york", "nova iorque", "new york")),
    ("America/Los_Angeles", ("los angeles", "califórnia", "são francisco")),
    ("America/Chicago", ("chicago",)),
    ("America/Mexico_City", ("cidade do méxico", "méxico")),
    ("America/Argentina/Buenos_Aires", ("buenos aires", "argentina")),
    ("America/Santiago", ("santiago", "chile")),
    ("America/Montevideo", ("montevidéu", "uruguai")),
    ("Asia/Tokyo", ("tóquio", "japão")),
    ("Asia/Shanghai", ("xangai", "pequim", "china")),
    ("Asia/Dubai", ("dubai",)),
    ("Australia/Sydney", ("sydney", "austrália")),
    ("Africa/Luanda", ("luanda", "angola")),
    ("UTC", ("utc", "tempo universal")),
)


def resolve_timezone(location: str = "", timezone_iana: str = "") -> Optional[str]:
    """
    Resolve an IANA identifier from what the LLM extracted, or ``None`` when
    nothing resolves with certainty.
    """
    if is_valid_timezone(timezone_iana):
        return timezone_iana.strip()

    if not location or not location.strip():
        return None

    matches: List[Tuple[str, Tuple[str, ...]]] = find_by_term(
        location, list(_CURATED_TIMEZONES), lambda entry: list(entry[1])
    )
    resolved = {entry[0] for entry in matches}
    if len(resolved) != 1:
        return None
    return resolved.pop()

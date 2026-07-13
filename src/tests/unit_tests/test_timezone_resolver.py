"""
domain/services/timezone_resolver.py tests (TDD) — §10.3 of the user-timezone plan.

Contract:

    resolve_timezone(location: str = "", timezone_iana: str = "") -> str | None

Python is the authority, never the LLM (§3.5). The pipeline the tests pin down:

  1. ``timezone_iana`` is used ONLY when it exists in
     ``zoneinfo.available_timezones()`` — a plausible hallucination
     ("America/Sao_Paolo") is discarded, not persisted;
  2. otherwise ``location`` is normalized (accents/case) and looked up in the
     curated pt-BR dictionary, with a fuzzy fallback via
     ``text_matching.find_by_term`` (so a typo still resolves);
  3. nothing resolves -> ``None``. The resolver never guesses.

Pure functions, no I/O, fully deterministic.
"""

import pytest

from domain.services.timezone_resolver import resolve_timezone


class TestResolveCityToIana:
    def test_sao_paulo__returns_america_sao_paulo(self):
        assert resolve_timezone(location="São Paulo") == "America/Sao_Paulo"

    def test_brasilia__returns_america_sao_paulo(self):
        # "Brasília" and "horário de brasília" are curated aliases of the same
        # IANA zone — the user never says "America/Sao_Paulo" out loud.
        assert resolve_timezone(location="Brasília") == "America/Sao_Paulo"
        assert (
            resolve_timezone(location="horário de brasília") == "America/Sao_Paulo"
        )

    @pytest.mark.parametrize(
        "location",
        ["São Paulo", "sao paulo", "SÃO PAULO", "  São paulo  ", "Sao Paulo"],
    )
    def test_accents_and_case_insensitive(self, location):
        assert resolve_timezone(location=location) == "America/Sao_Paulo"

    def test_lisboa__returns_europe_lisbon(self):
        assert resolve_timezone(location="Lisboa") == "Europe/Lisbon"

    @pytest.mark.parametrize(
        "location,expected",
        [
            ("Nova York", "America/New_York"),
            ("Nova Iorque", "America/New_York"),
            ("Manaus", "America/Manaus"),
            ("Fernando de Noronha", "America/Noronha"),
            ("Londres", "Europe/London"),
            ("Tóquio", "Asia/Tokyo"),
        ],
    )
    def test_curated_dictionary__resolves_known_cities(self, location, expected):
        assert resolve_timezone(location=location) == expected

    def test_fuzzy_typo__sao_paolo__resolves(self):
        # The user (or a transcription) typo'd the city; find_by_term's fuzzy
        # layer still lands on the right zone.
        assert resolve_timezone(location="Sao Paolo") == "America/Sao_Paulo"

    def test_unknown_city__returns_none(self):
        # No guessing: an unknown place resolves to nothing and the caller asks
        # the user for a reference city.
        assert resolve_timezone(location="Xurupitalândia do Norte") is None

    def test_empty_inputs__returns_none(self):
        assert resolve_timezone() is None
        assert resolve_timezone(location="", timezone_iana="") is None
        assert resolve_timezone(location="   ") is None

    def test_iana_passthrough__valid_identifier_accepted(self):
        assert resolve_timezone(timezone_iana="America/Bahia") == "America/Bahia"

    def test_iana_passthrough__invalid_identifier__none(self):
        # gemma4 invents plausible-looking identifiers; Python is the authority.
        assert resolve_timezone(timezone_iana="America/Sao_Paolo") is None
        assert resolve_timezone(timezone_iana="Europe/Lisboa") is None

    def test_hallucinated_iana__falls_back_to_the_location(self):
        # The most important case of the hybrid pipeline (§3.5): a bogus IANA is
        # dropped, and the faithfully transcribed location still resolves.
        assert (
            resolve_timezone(location="São Paulo", timezone_iana="America/Sao_Paolo")
            == "America/Sao_Paulo"
        )
        assert (
            resolve_timezone(location="Lisboa", timezone_iana="Europe/Lisboa")
            == "Europe/Lisbon"
        )

    def test_valid_iana__wins_over_the_location(self):
        # Step 1 short-circuits: a valid IANA is trusted as-is.
        assert (
            resolve_timezone(location="São Paulo", timezone_iana="Europe/Lisbon")
            == "Europe/Lisbon"
        )

    def test_hallucinated_iana_and_unknown_location__returns_none(self):
        assert (
            resolve_timezone(
                location="Xurupitalândia do Norte",
                timezone_iana="America/Xurupitalandia",
            )
            is None
        )

"""
SmartHomeService.find_entity_ids_by_alias Unit Tests (TDD).

Specification for a NEW deterministic alias matcher that resolves a single
device query against an {alias: entity_id} dict, without any LLM call and
without touching any repository.

Matching rules under test:
  - Accent/case insensitive (reuses the _normalize NFD+lower+strip pattern).
  - Stopwords ignored: "do", "da", "de", "o", "a", "no", "na".
  - Equipment synonyms treated as equivalent: "ar", "ar condicionado",
    "ar-condicionado", "climatizador", "split", "ac", "condicionado".
  - Match is by room/location token(s): a query that names the room matches
    the device of that room.
  - One query == one device: returns [entity_id] on a single match, [] on no
    match, and [] on ambiguity (more than one candidate for the same room).

The method does NOT exist yet — these tests will fail (AttributeError) until
the matcher is implemented. That is the expected TDD red state.
"""

from unittest.mock import AsyncMock, MagicMock

from domain.services.smart_home_service import SmartHomeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> SmartHomeService:
    """
    Build a SmartHomeService with all repositories mocked. The matcher is a
    pure function over the passed-in dict, so the repositories must never be
    touched; they exist only to satisfy the constructor signature.
    """
    return SmartHomeService(
        smart_home_light_repository=AsyncMock(),
        smart_home_configuration_repository=AsyncMock(),
        smart_home_entity_alias_repository=MagicMock(),
        smart_home_climate_repository=AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFindEntityIdsByAlias:
    def test_find_by_alias__partial_room_match__returns_entity_id(self):
        """'ar do quarto' must match 'Ar Condicionado do Quarto' by room."""
        service = _make_service()
        available = {"Ar Condicionado do Quarto": "climate.quarto"}

        result = service.find_entity_ids_by_alias(
            query_alias="ar do quarto", available_entities=available
        )

        assert result == ["climate.quarto"]

    def test_find_by_alias__exact_alias__returns_entity_id(self):
        """An exact alias string must match its entity_id."""
        service = _make_service()
        available = {"Ar Condicionado do Quarto": "climate.quarto"}

        result = service.find_entity_ids_by_alias(
            query_alias="Ar Condicionado do Quarto", available_entities=available
        )

        assert result == ["climate.quarto"]

    def test_find_by_alias__equipment_synonym__matches_same_room(self):
        """'climatizador da sala' must match 'Ar da Sala' (equipment synonym)."""
        service = _make_service()
        available = {"Ar da Sala": "climate.sala"}

        result = service.find_entity_ids_by_alias(
            query_alias="climatizador da sala", available_entities=available
        )

        assert result == ["climate.sala"]

    def test_find_by_alias__nonexistent_device__returns_empty_list(self):
        """A query for a room with no matching device must return []."""
        service = _make_service()
        available = {
            "Ar Condicionado do Quarto": "climate.quarto",
            "Ar da Sala": "climate.sala",
        }

        result = service.find_entity_ids_by_alias(
            query_alias="ar do banheiro", available_entities=available
        )

        assert result == []

    def test_find_by_alias__empty_dict__returns_empty_list(self):
        """An empty catalog must always return []."""
        service = _make_service()

        result = service.find_entity_ids_by_alias(
            query_alias="ar do quarto", available_entities={}
        )

        assert result == []

    def test_find_by_alias__ambiguous_room__returns_empty_list(self):
        """
        Ambiguity policy (documented expectation): when a generic query
        ('ar do quarto') could match more than one device in the same room
        ('Ar do Quarto Suíte', 'Ar do Quarto Hóspedes'), the matcher must
        refuse and return [] rather than guess. A single query maps to a
        single device; if it cannot be disambiguated, no device is acted on.
        """
        service = _make_service()
        available = {
            "Ar do Quarto Suíte": "climate.suite",
            "Ar do Quarto Hóspedes": "climate.hospedes",
        }

        result = service.find_entity_ids_by_alias(
            query_alias="ar do quarto", available_entities=available
        )

        assert result == []

    def test_find_by_alias__case_and_accent_insensitive__returns_entity_id(self):
        """'AR DA SALA' (uppercase) must match 'Ar da Sala'."""
        service = _make_service()
        available = {"Ar da Sala": "climate.sala"}

        result = service.find_entity_ids_by_alias(
            query_alias="AR DA SALA", available_entities=available
        )

        assert result == ["climate.sala"]

    def test_find_by_alias__does_not_touch_repositories(self):
        """
        The matcher is a pure function over the passed-in dict: it must not
        call any repository (no DB / no HA access).
        """
        service = _make_service()
        available = {"Ar da Sala": "climate.sala"}

        service.find_entity_ids_by_alias(
            query_alias="ar da sala", available_entities=available
        )

        service.smart_home_entity_alias_repository.get_all.assert_not_called()
        service.smart_home_climate_repository.get_state.assert_not_called()

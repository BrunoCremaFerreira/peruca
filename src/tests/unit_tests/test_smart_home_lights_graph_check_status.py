"""
SmartHomeLightsGraph check_status Unit Tests (TDD — RED).

Covers a NEW feature: querying the state of a SINGLE light by its spoken alias
("A luz da garagem está ligada?"), producing a short deterministic reply.

Two units under test (neither exists yet — expected RED by ABSENCE):

  1. SmartHomeLightsGraph._handle_check_status(data)
       - Reads data.get("output_check_status") (the spoken alias/phrase).
       - Empty/None payload -> returns {} (no action, service not called).
       - Delegates resolution to smart_home_service.get_light_status_by_alias
         (a coroutine, invoked through infra.async_runner.run — mocked here as
         an AsyncMock, mirroring the existing handler mocks for light_turn_on /
         light_turn_off).
       - Builds a deterministic phrase and returns {"output_check_status": phrase}:
             is_on True         -> "Sim, a luz {nome} está ligada."
             is_on False        -> "A luz {nome} está desligada."
             is_available False -> "A luz {nome} parece estar offline."
             not resolved (None)-> "Não encontrei o dispositivo '{alias}'."
         where {nome} = friendly_name OR the spoken alias — NEVER the entity_id.

  2. SmartHomeLightsGraph._classify_intent
       - A JSON payload {"check_status": "luz da garagem",
         "intents": ["check_status"]} must surface intent=['check_status'] and
         state["output_check_status"] == "luz da garagem".
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from domain.entities import SmartHomeLight


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> SmartHomeLightsGraph:
    """
    Build a SmartHomeLightsGraph with all external dependencies mocked.
    smart_home_service.get_light_status_by_alias is an AsyncMock because the
    handler runs it through async_runner.run(...), exactly like the existing
    light_turn_on / light_turn_off handlers.
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.get_light_status_by_alias = AsyncMock()
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeLightsGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeLightsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _state(**kwargs) -> dict:
    """Build a minimal graph state dict with sensible None defaults."""
    defaults = {
        "input": "",
        "intent": [],
        "output_check_status": None,
        "output_not_recognized": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


def _light(
    entity_id: str = "light.garagem",
    is_on: bool = True,
    is_available: bool = True,
    friendly_name: str = "Garagem",
) -> SmartHomeLight:
    """Build a SmartHomeLight for use as the mocked service return value."""
    return SmartHomeLight(
        entity_id=entity_id,
        is_on=is_on,
        is_available=is_available,
        friendly_name=friendly_name,
    )


def _configure_cleaned_output(graph: SmartHomeLightsGraph, cleaned_str: str) -> None:
    """
    Bypass the LLM call: patch _remove_thinking_tag so _classify_intent's
    structured-output extraction receives cleaned_str verbatim (same trick used
    by test_smart_home_lights_graph_classify_intent.py).
    """
    graph._remove_thinking_tag = MagicMock(return_value=cleaned_str)


# ===========================================================================
# TestHandleCheckStatus — deterministic phrases
# ===========================================================================


class TestHandleCheckStatus:
    def test_handle_check_status__light_on__returns_ligada_phrase(self):
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(is_on=True, is_available=True, friendly_name="Garagem")
        )
        state = _state(output_check_status="luz da garagem")

        result = graph._handle_check_status(state)

        assert result == {
            "output_check_status": "Sim, a luz Garagem está ligada."
        }, f"Unexpected phrase for on-light: {result!r}"

    def test_handle_check_status__light_off__returns_desligada_phrase(self):
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(is_on=False, is_available=True, friendly_name="Garagem")
        )
        state = _state(output_check_status="luz da garagem")

        result = graph._handle_check_status(state)

        assert result == {
            "output_check_status": "A luz Garagem está desligada."
        }, f"Unexpected phrase for off-light: {result!r}"

    def test_handle_check_status__light_offline__returns_offline_phrase(self):
        """is_available False must win even if is_on is set/stale."""
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(is_on=True, is_available=False, friendly_name="Garagem")
        )
        state = _state(output_check_status="luz da garagem")

        result = graph._handle_check_status(state)

        assert result == {
            "output_check_status": "A luz Garagem parece estar offline."
        }, f"Unexpected phrase for offline-light: {result!r}"

    def test_handle_check_status__not_resolved__returns_nao_encontrado_phrase(self):
        """When the service returns None the reply must name the spoken alias."""
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=None
        )
        state = _state(output_check_status="garagem")

        result = graph._handle_check_status(state)

        assert result == {
            "output_check_status": "Não encontrei o dispositivo 'garagem'."
        }, f"Unexpected phrase for unresolved device: {result!r}"

    def test_handle_check_status__no_friendly_name__uses_spoken_alias_as_name(self):
        """When friendly_name is None the phrase falls back to the spoken alias."""
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(is_on=True, is_available=True, friendly_name=None)
        )
        state = _state(output_check_status="cozinha")

        result = graph._handle_check_status(state)

        assert result == {
            "output_check_status": "Sim, a luz cozinha está ligada."
        }, f"Expected the spoken alias as the name, got: {result!r}"

    def test_handle_check_status__on__never_leaks_entity_id(self):
        """Regression: the reply must never expose the raw entity_id."""
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(
                entity_id="light.garagem", is_on=True, friendly_name="Garagem"
            )
        )
        state = _state(output_check_status="luz da garagem")

        result = graph._handle_check_status(state)

        assert "light.garagem" not in result["output_check_status"], (
            f"entity_id leaked into the reply: {result!r}"
        )

    def test_handle_check_status__empty_payload__returns_empty_dict(self):
        graph = _make_graph()
        state = _state(output_check_status=None)

        result = graph._handle_check_status(state)

        assert result == {}, f"Expected empty dict for None payload, got: {result}"
        graph.smart_home_service.get_light_status_by_alias.assert_not_called()

    def test_handle_check_status__output_key_is_output_check_status(self):
        """The handler must write to 'output_check_status', not another key."""
        graph = _make_graph()
        graph.smart_home_service.get_light_status_by_alias = AsyncMock(
            return_value=_light(is_on=True, friendly_name="Garagem")
        )
        state = _state(output_check_status="luz da garagem")

        result = graph._handle_check_status(state)

        assert "output_check_status" in result, (
            f"Expected key 'output_check_status', got keys: {list(result.keys())}"
        )


# ===========================================================================
# TestClassifyIntentCheckStatus — classifier surfaces the new intent/field
# ===========================================================================


class TestClassifyIntentCheckStatus:
    def test_classify__check_status__sets_intent_and_output(self):
        """
        LLM returns {'intents': ['check_status'], 'check_status': 'luz da garagem'}.
        State must carry the intent and output_check_status='luz da garagem'.
        """
        graph = _make_graph()
        json_payload = (
            '{"intents": ["check_status"], "check_status": "luz da garagem"}'
        )
        _configure_cleaned_output(graph, json_payload)

        result = graph._classify_intent({"input": "a luz da garagem está ligada?"})

        assert "check_status" in result["intent"], (
            f"Expected 'check_status' in intent list, got {result['intent']!r}"
        )
        assert result.get("output_check_status") == "luz da garagem", (
            f"Expected output_check_status='luz da garagem', got {result!r}"
        )

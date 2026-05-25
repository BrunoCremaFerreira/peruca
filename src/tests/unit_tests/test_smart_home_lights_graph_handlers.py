import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph


"""
SmartHomeLightsGraph handler unit tests.

Covers the following behaviour changes (TDD — written before implementation):

  1. _handle_final_response must return a descriptive string in `output`,
     not a dict.

  2. _handle_turn_on must return {"output_turn_on": "Dispositivo nao encontrado"}
     when no entity_id is found (was "Device not found").

  3. _handle_turn_off must return {"output_turn_off": "Dispositivo nao encontrado"}
     when no entity_id is found (was "Device not found").
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph() -> SmartHomeLightsGraph:
    """
    Build a SmartHomeLightsGraph with all external dependencies mocked.
    load_prompt is patched to avoid filesystem access.
    smart_home_service uses AsyncMock because the handlers call
    asyncio.run(service.light_turn_on(...)) / asyncio.run(service.light_turn_off(...)).
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.light_turn_on = AsyncMock()
    smart_home_service.light_turn_off = AsyncMock()
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
        "output_turn_on": None,
        "output_turn_off": None,
        "output_change_color": None,
        "output_change_bright": None,
        "output_change_mode": None,
        "output_not_recognized": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Mudança 1 — _handle_final_response returns a descriptive string
# ---------------------------------------------------------------------------

class TestHandleFinalResponseOutputFormat:

    def test_handle_final_response__only_turn_on__returns_ligado_string(self):
        graph = _make_graph()
        state = _state(output_turn_on="luz da sala")

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str), (
            f"Expected str, got {type(result['output'])}"
        )
        assert "Ligado" in result["output"]
        assert "luz da sala" in result["output"]

    def test_handle_final_response__only_turn_off__returns_desligado_string(self):
        graph = _make_graph()
        state = _state(output_turn_off="luz do quarto")

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str)
        assert "Desligado" in result["output"]
        assert "luz do quarto" in result["output"]

    def test_handle_final_response__turn_on_and_turn_off__returns_combined_string(self):
        graph = _make_graph()
        state = _state(output_turn_on="sala", output_turn_off="quarto")

        result = graph._handle_final_response(state)

        output = result["output"]
        assert isinstance(output, str)
        assert "Ligado" in output
        assert "sala" in output
        assert "Desligado" in output
        assert "quarto" in output

    def test_handle_final_response__all_outputs_empty_or_none__returns_nenhuma_acao(self):
        graph = _make_graph()
        state = _state()

        result = graph._handle_final_response(state)

        assert result["output"] == "Nenhuma acao executada"

    def test_handle_final_response__output_not_recognized_truthy__returns_dispositivo_nao_reconhecido(self):
        graph = _make_graph()
        state = _state(output_not_recognized="Not Recognized Triggered")

        result = graph._handle_final_response(state)

        assert result["output"] == "Dispositivo nao reconhecido"

    def test_handle_final_response__output_is_not_a_dict(self):
        """Regression: previous implementation returned a dict. Must now be str."""
        graph = _make_graph()
        state = _state(output_turn_on="sala")

        result = graph._handle_final_response(state)

        assert not isinstance(result["output"], dict), (
            "output must not be a dict — it must be a human-readable string"
        )


# ---------------------------------------------------------------------------
# Mudança 2 — _handle_turn_on: device not found message in Portuguese
# ---------------------------------------------------------------------------

class TestHandleTurnOnDeviceNotFound:

    def test_handle_turn_on__entity_not_found__returns_dispositivo_nao_encontrado(self):
        graph = _make_graph()
        # _find_entity_ids is patched to simulate no match
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_on="luz inexistente", available_entities={})

        result = graph._handle_turn_on(state)

        assert result == {"output_turn_on": "Dispositivo nao encontrado"}, (
            f"Expected Portuguese message, got: {result}"
        )

    def test_handle_turn_on__entity_not_found__does_not_return_english_message(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_on="luz inexistente", available_entities={})

        result = graph._handle_turn_on(state)

        assert result.get("output_turn_on") != "Device not found", (
            "English fallback message must be replaced with Portuguese"
        )

    def test_handle_turn_on__entity_found__calls_service_and_returns_device_name(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["light.sala"])
        state = _state(output_turn_on="sala", available_entities={"sala": "light.sala"})

        result = graph._handle_turn_on(state)

        graph.smart_home_service.light_turn_on.assert_called_once()
        assert result.get("output_turn_on") == "sala"

    def test_handle_turn_on__empty_devices__returns_empty_dict(self):
        graph = _make_graph()
        state = _state(output_turn_on=None)

        result = graph._handle_turn_on(state)

        assert result == {}


# ---------------------------------------------------------------------------
# Mudança 3 — _handle_turn_off: device not found message in Portuguese
# ---------------------------------------------------------------------------

class TestHandleTurnOffDeviceNotFound:

    def test_handle_turn_off__entity_not_found__returns_dispositivo_nao_encontrado(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_off="luz inexistente", available_entities={})

        result = graph._handle_turn_off(state)

        assert result == {"output_turn_off": "Dispositivo nao encontrado"}, (
            f"Expected Portuguese message, got: {result}"
        )

    def test_handle_turn_off__entity_not_found__does_not_return_english_message(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_off="luz inexistente", available_entities={})

        result = graph._handle_turn_off(state)

        assert result.get("output_turn_off") != "Device not found"

    def test_handle_turn_off__entity_found__calls_service_and_returns_device_name(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=["light.quarto"])
        state = _state(output_turn_off="quarto", available_entities={"quarto": "light.quarto"})

        result = graph._handle_turn_off(state)

        graph.smart_home_service.light_turn_off.assert_called_once()
        assert result.get("output_turn_off") == "quarto"

    def test_handle_turn_off__empty_devices__returns_empty_dict(self):
        graph = _make_graph()
        state = _state(output_turn_off=None)

        result = graph._handle_turn_off(state)

        assert result == {}

    def test_handle_turn_off__entity_not_found__key_is_output_turn_off_not_output_turn_on(self):
        """
        Regression: original code incorrectly returned {"output_turn_on": "Device not found"}
        when the turn_off handler could not find the entity.
        The correct key must be output_turn_off.
        """
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_off="luz inexistente", available_entities={})

        result = graph._handle_turn_off(state)

        assert "output_turn_off" in result, (
            "turn_off handler must use key 'output_turn_off', not 'output_turn_on'"
        )
        assert "output_turn_on" not in result

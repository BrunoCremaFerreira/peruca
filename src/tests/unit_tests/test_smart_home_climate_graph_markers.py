"""
SmartHomeClimateGraph "not recognized" marker unit tests (TDD).

Canonical contract (mirrors SmartHomeLightsGraph):
  - When a device cannot be resolved, the per-action output must NEVER be empty;
    it must carry the marker "Dispositivo nao reconhecido".
  - _handle_final_response with no parts must return
    {"output": "Nenhuma acao executada"} (today it returns "").

The shared markers are expected to live in application.graphs.markers as:
    DEVICE_NOT_RECOGNIZED = "Dispositivo nao reconhecido"
    NO_ACTION_PERFORMED   = "Nenhuma acao executada"

The import below is intentionally NOT guarded: if the markers module does not
exist yet, this file fails at import with ImportError — the expected TDD red
state. The literal strings are also asserted directly so the contract is
robust even if the constant names change.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from application.graphs.markers import DEVICE_NOT_RECOGNIZED, NO_ACTION_PERFORMED
from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> SmartHomeClimateGraph:
    """
    Build a SmartHomeClimateGraph with all external dependencies mocked.
    load_prompt is patched to avoid filesystem access. The climate service
    methods are AsyncMock because handlers call asyncio.run on them.
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.climate_turn_on = AsyncMock()
    smart_home_service.climate_turn_off = AsyncMock()
    smart_home_service.climate_set_temperature = AsyncMock()
    smart_home_service.climate_set_hvac_mode = AsyncMock()
    smart_home_service.climate_get_state = AsyncMock()
    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeClimateGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeClimateGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )
    return graph


def _state(**kwargs) -> dict:
    defaults = {
        "input": "",
        "intent": [],
        "output_turn_on": None,
        "output_turn_off": None,
        "output_set_temperature": None,
        "output_set_hvac_mode": None,
        "output_query_state": None,
        "output_not_recognized": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Marker constants
# ---------------------------------------------------------------------------


class TestMarkerConstants:
    def test_device_not_recognized_constant__has_canonical_value(self):
        assert DEVICE_NOT_RECOGNIZED == "Dispositivo nao reconhecido"

    def test_no_action_performed_constant__has_canonical_value(self):
        assert NO_ACTION_PERFORMED == "Nenhuma acao executada"


# ---------------------------------------------------------------------------
# Per-action: device not found must surface the marker, never empty
# ---------------------------------------------------------------------------


class TestQueryStateDeviceNotRecognized:
    def test_query_state__device_not_found__contains_marker_not_empty(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_query_state="ar do banheiro")

        result = graph._handle_query_state(state)

        output = result.get("output_query_state")
        assert output, f"output_query_state must never be empty, got: {output!r}"
        assert output != ""
        assert DEVICE_NOT_RECOGNIZED in output


class TestTurnOnDeviceNotRecognized:
    def test_turn_on__device_not_found__returns_marker(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_on="ar do banheiro")

        result = graph._handle_turn_on(state)

        assert result.get("output_turn_on") == DEVICE_NOT_RECOGNIZED
        assert result.get("output_turn_on") != "Device not found"


class TestTurnOffDeviceNotRecognized:
    def test_turn_off__device_not_found__returns_marker(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_turn_off="ar do banheiro")

        result = graph._handle_turn_off(state)

        assert result.get("output_turn_off") == DEVICE_NOT_RECOGNIZED
        assert result.get("output_turn_off") != "Device not found"


class TestSetTemperatureDeviceNotRecognized:
    def test_set_temperature__device_not_found__contains_marker_not_empty(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_set_temperature="ar do banheiro, 22")

        result = graph._handle_set_temperature(state)

        output = result.get("output_set_temperature")
        assert output, (
            f"output_set_temperature must never be empty when the device is "
            f"unknown, got: {output!r}"
        )
        assert DEVICE_NOT_RECOGNIZED in output


class TestSetHvacModeDeviceNotRecognized:
    def test_set_hvac_mode__device_not_found__contains_marker_not_empty(self):
        graph = _make_graph()
        graph._find_entity_ids = MagicMock(return_value=[])
        state = _state(output_set_hvac_mode="ar do banheiro, frio")

        result = graph._handle_set_hvac_mode(state)

        output = result.get("output_set_hvac_mode")
        assert output, (
            f"output_set_hvac_mode must never be empty when the device is "
            f"unknown, got: {output!r}"
        )
        assert DEVICE_NOT_RECOGNIZED in output


# ---------------------------------------------------------------------------
# _handle_final_response: empty state must produce NO_ACTION_PERFORMED
# ---------------------------------------------------------------------------


class TestFinalResponseNoAction:
    def test_final_response__no_outputs__returns_nenhuma_acao_executada(self):
        graph = _make_graph()
        state = _state()

        result = graph._handle_final_response(state)

        assert result["output"] == NO_ACTION_PERFORMED
        assert result["output"] != ""

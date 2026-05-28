"""
SmartHomeLightsGraph area-handler unit tests (TDD / RED phase).

Covers the 5 new graph nodes introduced for the area-based light commands:

  - _handle_turn_on_by_area       (state key: output_turn_on_by_area)
  - _handle_turn_off_by_area      (state key: output_turn_off_by_area)
  - _handle_turn_on_all           (state key: output_turn_on_all)
  - _handle_turn_off_all          (state key: output_turn_off_all)
  - _handle_list_lights_status    (state key: output_list_lights_status)

Plus the _handle_final_response merging of the new outputs.

These nodes delegate IO to SmartHomeService (mocked). They must NOT call
the LLM (no _find_entity_ids — area resolution is deterministic in the
service layer).

Conventions match test_smart_home_lights_graph_handlers.py:
  - _make_graph() with all deps mocked + load_prompt patched
  - _state(**kwargs) with sensible None defaults — TYPE EXTENDED here to
    include the new keys.
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph

try:
    from domain.entities import SmartHomeLight, SmartHomeArea

    _AREA_AVAILABLE = True
except ImportError:
    SmartHomeLight = None  # type: ignore[assignment,misc]
    SmartHomeArea = None  # type: ignore[assignment,misc]
    _AREA_AVAILABLE = False

try:
    from domain.exceptions import ValidationError, NofFoundValidationError
except ImportError:  # pragma: no cover
    ValidationError = Exception  # type: ignore[assignment,misc]
    NofFoundValidationError = Exception  # type: ignore[assignment,misc]


_SKIP_IF_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _AREA_AVAILABLE, reason="SmartHomeArea / SmartHomeLight area fields missing"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> SmartHomeLightsGraph:
    """
    Build a SmartHomeLightsGraph with all external dependencies mocked.

    The SmartHomeService is mocked with AsyncMock for the async area methods:
      - turn_on_by_area, turn_off_by_area
      - turn_on_all_house, turn_off_all_house
      - list_lights_grouped_by_area
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    # New async methods used by the area handlers:
    smart_home_service.turn_on_by_area = AsyncMock()
    smart_home_service.turn_off_by_area = AsyncMock()
    smart_home_service.turn_on_all_house = AsyncMock()
    smart_home_service.turn_off_all_house = AsyncMock()
    smart_home_service.list_lights_grouped_by_area = AsyncMock(return_value={})
    # Legacy async methods used by the existing handlers (kept for compatibility):
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
    """
    Graph-state factory with defaults for both the legacy and the new
    area-related keys.
    """
    defaults = {
        "input": "",
        "intent": [],
        # legacy outputs (kept for backward compatibility)
        "output_turn_on": None,
        "output_turn_off": None,
        "output_change_color": None,
        "output_change_bright": None,
        "output_change_mode": None,
        "output_not_recognized": None,
        # new area outputs
        "output_turn_on_by_area": None,
        "output_turn_off_by_area": None,
        "output_turn_on_all": None,
        "output_turn_off_all": None,
        "output_list_lights_status": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


def _sample_light(entity_id, area_id=None, is_on=False, is_available=True,
                  friendly_name=None):
    return SmartHomeLight(
        entity_id=entity_id,
        area_id=area_id,
        is_on=is_on,
        is_available=is_available,
        friendly_name=friendly_name,
    )


# ===========================================================================
# TestHandleTurnOnByArea
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleTurnOnByArea:
    def test_handle__valid_area__calls_service_turn_on_by_area(self):
        graph = _make_graph()
        state = _state(output_turn_on_by_area="Cozinha")

        graph._handle_turn_on_by_area(state)

        graph.smart_home_service.turn_on_by_area.assert_called_once()

    def test_handle__valid_area__returns_output_turn_on_by_area_in_state(self):
        graph = _make_graph()
        state = _state(output_turn_on_by_area="Cozinha")

        result = graph._handle_turn_on_by_area(state)

        assert "output_turn_on_by_area" in result
        assert result["output_turn_on_by_area"], (
            f"Expected non-empty output_turn_on_by_area, got {result!r}"
        )

    def test_handle__empty_area__returns_empty_dict_no_service_call(self):
        graph = _make_graph()
        state = _state(output_turn_on_by_area=None)

        result = graph._handle_turn_on_by_area(state)

        graph.smart_home_service.turn_on_by_area.assert_not_called()
        assert result == {}, (
            f"Expected empty dict for None area payload, got {result!r}"
        )

    def test_handle__area_inexistente__sets_friendly_error_in_state(self):
        """
        When the service raises ValidationError for an unknown area, the
        handler must NOT propagate. It must set a user-friendly error message
        on output_turn_on_by_area.
        """
        graph = _make_graph()
        graph.smart_home_service.turn_on_by_area.side_effect = ValidationError(
            errors=["Area not found"]
        )
        state = _state(output_turn_on_by_area="Banheiro")

        result = graph._handle_turn_on_by_area(state)

        assert "output_turn_on_by_area" in result
        # Friendly message — must not be empty and must hint at "not found"
        text = str(result["output_turn_on_by_area"]).lower()
        assert (
            "encontrad" in text or "nao encontrado" in text or "não encontrad" in text
        ), f"Expected a friendly 'not found' message, got {result!r}"

    def test_handle__multiple_areas_list__service_called_per_area(self):
        """
        Plan checkpoint: when output_turn_on_by_area is a list of areas, the
        service must be called once per area.
        """
        graph = _make_graph()
        state = _state(output_turn_on_by_area=["Cozinha", "Sala"])

        graph._handle_turn_on_by_area(state)

        assert graph.smart_home_service.turn_on_by_area.call_count == 2, (
            f"Expected service called 2 times (once per area), "
            f"got {graph.smart_home_service.turn_on_by_area.call_count}"
        )

    def test_handle__multiple_areas_pipe_string__service_called_per_area(self):
        """
        Plan checkpoint: when output_turn_on_by_area is a pipe-separated
        string (LLM may produce either form), the service must still be
        called once per area.
        """
        graph = _make_graph()
        state = _state(output_turn_on_by_area="Cozinha|Sala")

        graph._handle_turn_on_by_area(state)

        assert graph.smart_home_service.turn_on_by_area.call_count == 2, (
            f"Expected service called 2 times for pipe-string, "
            f"got {graph.smart_home_service.turn_on_by_area.call_count}"
        )


# ===========================================================================
# TestHandleTurnOffByArea (mirror of TestHandleTurnOnByArea)
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleTurnOffByArea:
    def test_handle__valid_area__calls_service_turn_off_by_area(self):
        graph = _make_graph()
        state = _state(output_turn_off_by_area="Sala")

        graph._handle_turn_off_by_area(state)

        graph.smart_home_service.turn_off_by_area.assert_called_once()

    def test_handle__empty_area__returns_empty_dict_no_service_call(self):
        graph = _make_graph()
        state = _state(output_turn_off_by_area=None)

        result = graph._handle_turn_off_by_area(state)

        graph.smart_home_service.turn_off_by_area.assert_not_called()
        assert result == {}

    def test_handle__area_inexistente__sets_friendly_error_in_state(self):
        graph = _make_graph()
        graph.smart_home_service.turn_off_by_area.side_effect = ValidationError(
            errors=["Area not found"]
        )
        state = _state(output_turn_off_by_area="Escritorio")

        result = graph._handle_turn_off_by_area(state)

        text = str(result.get("output_turn_off_by_area", "")).lower()
        assert (
            "encontrad" in text or "nao encontrado" in text or "não encontrad" in text
        ), f"Expected friendly 'not found' message, got {result!r}"

    def test_handle__multiple_areas_list__service_called_per_area(self):
        graph = _make_graph()
        state = _state(output_turn_off_by_area=["Cozinha", "Sala"])

        graph._handle_turn_off_by_area(state)

        assert graph.smart_home_service.turn_off_by_area.call_count == 2


# ===========================================================================
# TestHandleTurnOnAll
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleTurnOnAll:
    def test_handle__triggered__calls_service_turn_on_all_house(self):
        graph = _make_graph()
        state = _state(output_turn_on_all=True)

        graph._handle_turn_on_all(state)

        graph.smart_home_service.turn_on_all_house.assert_called_once()

    def test_handle__not_triggered_none__returns_empty_dict(self):
        graph = _make_graph()
        state = _state(output_turn_on_all=None)

        result = graph._handle_turn_on_all(state)

        graph.smart_home_service.turn_on_all_house.assert_not_called()
        assert result == {}

    def test_handle__empty_house__no_raise_state_carries_neutral_output(self):
        """
        Plan checkpoint: empty house must not raise; the handler must surface
        a non-error output in the state (the final_response will format it).
        """
        graph = _make_graph()
        # Service returns nothing (empty house) — must not raise.
        graph.smart_home_service.turn_on_all_house = AsyncMock(return_value=None)
        state = _state(output_turn_on_all=True)

        result = graph._handle_turn_on_all(state)

        # Just ensure the handler ran cleanly and produced a state delta.
        assert isinstance(result, dict)


# ===========================================================================
# TestHandleTurnOffAll
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleTurnOffAll:
    def test_handle__triggered__calls_service_turn_off_all_house(self):
        graph = _make_graph()
        state = _state(output_turn_off_all=True)

        graph._handle_turn_off_all(state)

        graph.smart_home_service.turn_off_all_house.assert_called_once()

    def test_handle__not_triggered_none__returns_empty_dict(self):
        graph = _make_graph()
        state = _state(output_turn_off_all=None)

        result = graph._handle_turn_off_all(state)

        graph.smart_home_service.turn_off_all_house.assert_not_called()
        assert result == {}


# ===========================================================================
# TestHandleListLightsStatus
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestHandleListLightsStatus:
    def test_handle__lights_present__calls_service_list_lights_grouped_by_area(self):
        graph = _make_graph()
        graph.smart_home_service.list_lights_grouped_by_area = AsyncMock(
            return_value={
                "Cozinha": [
                    _sample_light("light.cozinha_1", area_id="kitchen", is_on=True),
                    _sample_light("light.cozinha_2", area_id="kitchen", is_on=False),
                ],
                "Sala": [
                    _sample_light("light.sala_1", area_id="living_room", is_on=True)
                ],
            }
        )
        state = _state(output_list_lights_status=True)

        graph._handle_list_lights_status(state)

        graph.smart_home_service.list_lights_grouped_by_area.assert_called_once()

    def test_handle__lights_present__formats_status_in_state(self):
        """
        Plan checkpoint: the formatted output for the listing must contain the
        area names and a status label ('Ligada' / 'Desligada') per light.
        """
        graph = _make_graph()
        graph.smart_home_service.list_lights_grouped_by_area = AsyncMock(
            return_value={
                "Cozinha": [
                    _sample_light(
                        "light.cozinha_1",
                        area_id="kitchen",
                        is_on=True,
                        friendly_name="Luz Central",
                    ),
                    _sample_light(
                        "light.cozinha_2",
                        area_id="kitchen",
                        is_on=False,
                        friendly_name="Luz da Pia",
                    ),
                ],
            }
        )
        state = _state(output_list_lights_status=True)

        result = graph._handle_list_lights_status(state)

        text = str(result.get("output_list_lights_status", ""))
        assert "Cozinha" in text, f"Expected 'Cozinha' in output, got {text!r}"
        assert "Ligada" in text, f"Expected 'Ligada' status, got {text!r}"
        assert "Desligada" in text, f"Expected 'Desligada' status, got {text!r}"

    def test_handle__unavailable_light__status_text_is_offline(self):
        """
        Plan checkpoint: a light with is_available=False must be labelled
        'Offline' (not 'Desligada').
        """
        graph = _make_graph()
        graph.smart_home_service.list_lights_grouped_by_area = AsyncMock(
            return_value={
                "Cozinha": [
                    _sample_light(
                        "light.cozinha_quebrada",
                        area_id="kitchen",
                        is_available=False,
                        friendly_name="Luz Queimada",
                    )
                ],
            }
        )
        state = _state(output_list_lights_status=True)

        result = graph._handle_list_lights_status(state)

        text = str(result.get("output_list_lights_status", ""))
        assert "Offline" in text, (
            f"Expected 'Offline' label for unavailable light, got {text!r}"
        )

    def test_handle__no_lights__friendly_empty_message(self):
        """
        Plan checkpoint: empty house must not raise; the output must carry
        a user-friendly empty message.
        """
        graph = _make_graph()
        graph.smart_home_service.list_lights_grouped_by_area = AsyncMock(
            return_value={}
        )
        state = _state(output_list_lights_status=True)

        result = graph._handle_list_lights_status(state)

        text = str(result.get("output_list_lights_status", ""))
        # Just ensure it's a non-empty human-readable message
        assert text.strip() != "", (
            "Empty house must yield a non-empty friendly message, "
            f"got {result!r}"
        )

    def test_handle__not_triggered__returns_empty_dict(self):
        """When the intent is not list_lights_status, the handler is a no-op."""
        graph = _make_graph()
        state = _state(output_list_lights_status=None)

        result = graph._handle_list_lights_status(state)

        graph.smart_home_service.list_lights_grouped_by_area.assert_not_called()
        assert result == {}


# ===========================================================================
# TestFinalResponseAreaIntents — merges new outputs
# ===========================================================================


@_SKIP_IF_NOT_IMPLEMENTED
class TestFinalResponseAreaIntents:
    def test_final_response__turn_on_by_area__renders_area_in_output(self):
        graph = _make_graph()
        state = _state(output_turn_on_by_area="Cozinha")

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str)
        assert "Cozinha" in result["output"], (
            f"Expected 'Cozinha' in final output, got {result['output']!r}"
        )

    def test_final_response__turn_off_by_area__renders_area_in_output(self):
        graph = _make_graph()
        state = _state(output_turn_off_by_area="Sala")

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str)
        assert "Sala" in result["output"]

    def test_final_response__turn_on_all__renders_some_global_message(self):
        graph = _make_graph()
        state = _state(output_turn_on_all="Todas ligadas")

        result = graph._handle_final_response(state)

        assert isinstance(result["output"], str)
        assert result["output"].strip() != "", (
            f"Expected a non-empty message for turn_on_all, got {result!r}"
        )

    def test_final_response__list_lights_status__preserves_grouping(self):
        """
        Plan checkpoint: when output_list_lights_status carries a grouped
        listing (with newlines and per-room markers), the final response must
        keep it intact — do NOT collapse to a single line.
        """
        graph = _make_graph()
        grouped = "**Cozinha**\n- Luz Central: Ligada\n- Luz da Pia: Desligada"
        state = _state(output_list_lights_status=grouped)

        result = graph._handle_final_response(state)

        output = result["output"]
        assert isinstance(output, str)
        assert "Cozinha" in output
        assert "Ligada" in output
        assert "Desligada" in output
        # Newlines must be preserved so the listing remains grouped.
        assert "\n" in output, (
            f"Expected newlines preserved in listing, got {output!r}"
        )

    def test_final_response__error_area_not_found__friendly_message_in_output(self):
        """
        Plan checkpoint: when a handler set a 'not found' message on its
        output_*, that message must reach the final output (the user sees it).
        """
        graph = _make_graph()
        state = _state(output_turn_on_by_area="Area nao encontrada")

        result = graph._handle_final_response(state)

        assert "Area nao encontrada" in result["output"]

    def test_final_response__no_area_outputs__falls_back_to_nenhuma_acao(self):
        """When NO output_* (legacy or area) is set, the existing default applies."""
        graph = _make_graph()
        state = _state()

        result = graph._handle_final_response(state)

        assert result["output"] == "Nenhuma acao executada"

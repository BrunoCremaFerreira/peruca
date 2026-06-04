"""
Milestone 2 — Parallel Execution via asyncio.gather (TDD)

These tests specify the CORRECTNESS contract for every handler that iterates
over a list of entity IDs and dispatches async service calls.

Current behaviour (BEFORE Milestone 2):
    for entity_id in entity_ids:
        asyncio.run(self.service.some_method(entity_id))

Target behaviour (AFTER Milestone 2):
    async def _run():
        await asyncio.gather(*[self.service.some_method(eid) for eid in entity_ids])
    asyncio.run(_run())

The tests do NOT inspect HOW the concurrency is achieved — they verify the
observable result: with N entity IDs the service mock must be called exactly N
times with the correct arguments.

Because the tests focus on correctness (call-count and call-args), they will
PASS against both the current loop implementation and the gather implementation.
If a bug is introduced — e.g. only the last entity is processed — these tests
will catch it.

Graphs under test
-----------------
1. SmartHomeLightsGraph  — _handle_turn_on, _handle_turn_off, _handle_change_bright
2. SmartHomeClimateGraph — _handle_turn_on, _handle_set_temperature, _handle_set_hvac_mode
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph
from domain.commands import LightTurnOn, ClimateTurnOn, ClimateSetTemperature, ClimateSetHvacMode


# ===========================================================================
# Shared helpers
# ===========================================================================


def _make_lights_graph() -> SmartHomeLightsGraph:
    """
    Build a SmartHomeLightsGraph with all external dependencies mocked.

    load_prompt is patched at construction time to avoid filesystem access.
    smart_home_service exposes AsyncMock for every method the handlers call
    so that asyncio.run(coro) does not block or raise.
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


def _make_climate_graph() -> SmartHomeClimateGraph:
    """
    Build a SmartHomeClimateGraph with all external dependencies mocked.
    """
    llm_chat = MagicMock()
    smart_home_service = MagicMock()
    smart_home_service.climate_turn_on = AsyncMock()
    smart_home_service.climate_turn_off = AsyncMock()
    smart_home_service.climate_set_temperature = AsyncMock()
    smart_home_service.climate_set_hvac_mode = AsyncMock()

    alias_repo = MagicMock()
    alias_repo.get_all.return_value = []

    with patch.object(SmartHomeClimateGraph, "load_prompt", return_value="{input}"):
        graph = SmartHomeClimateGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=alias_repo,
        )

    return graph


def _lights_state(**kwargs) -> dict:
    defaults = {
        "input": "",
        "intent": [],
        "output_turn_on": None,
        "output_turn_off": None,
        "output_change_bright": None,
        "output_change_color": None,
        "output_change_mode": None,
        "output_not_recognized": None,
        "available_entities": {},
        "output": None,
    }
    defaults.update(kwargs)
    return defaults


def _climate_state(**kwargs) -> dict:
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


# ===========================================================================
# SmartHomeLightsGraph — _handle_turn_on
# ===========================================================================


class TestLightsTurnOnMultipleEntities:
    """
    Verifies that _handle_turn_on calls light_turn_on once per entity ID
    returned by _find_entity_ids, and that every call carries the correct
    entity_id wrapped inside a LightTurnOn command.
    """

    def test_handle_turn_on__two_entities__service_called_twice(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["light.sala", "light.quarto"]
        )
        state = _lights_state(
            output_turn_on="sala|quarto",
            available_entities={"sala": "light.sala", "quarto": "light.quarto"},
        )

        graph._handle_turn_on(state)

        assert graph.smart_home_service.light_turn_on.call_count == 2, (
            f"Expected light_turn_on called 2 times for 2 entities, "
            f"got {graph.smart_home_service.light_turn_on.call_count}"
        )

    def test_handle_turn_on__two_entities__correct_entity_ids_used(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["light.sala", "light.quarto"]
        )
        state = _lights_state(
            output_turn_on="sala|quarto",
            available_entities={"sala": "light.sala", "quarto": "light.quarto"},
        )

        graph._handle_turn_on(state)

        calls = graph.smart_home_service.light_turn_on.call_args_list
        used_entity_ids = {
            (c.kwargs.get("turn_on_command") or c.args[0]).entity_id for c in calls
        }
        assert used_entity_ids == {"light.sala", "light.quarto"}, (
            f"Expected entity IDs {{'light.sala', 'light.quarto'}}, got {used_entity_ids}"
        )

    def test_handle_turn_on__three_entities__service_called_three_times(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["light.sala", "light.quarto", "light.cozinha"]
        )
        state = _lights_state(
            output_turn_on="sala|quarto|cozinha",
            available_entities={},
        )

        graph._handle_turn_on(state)

        assert graph.smart_home_service.light_turn_on.call_count == 3, (
            f"Expected 3 calls for 3 entities, "
            f"got {graph.smart_home_service.light_turn_on.call_count}"
        )

    def test_handle_turn_on__single_entity__service_called_once(self):
        """Baseline: single entity must still produce exactly one call."""
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(return_value=["light.sala"])
        state = _lights_state(output_turn_on="sala", available_entities={})

        graph._handle_turn_on(state)

        graph.smart_home_service.light_turn_on.assert_called_once()


# ===========================================================================
# SmartHomeLightsGraph — _handle_turn_off
# ===========================================================================


class TestLightsTurnOffMultipleEntities:
    """
    Verifies that _handle_turn_off calls light_turn_off once per entity ID.
    """

    def test_handle_turn_off__two_entities__service_called_twice(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["light.sala", "light.quarto"]
        )
        state = _lights_state(
            output_turn_off="sala|quarto",
            available_entities={"sala": "light.sala", "quarto": "light.quarto"},
        )

        graph._handle_turn_off(state)

        assert graph.smart_home_service.light_turn_off.call_count == 2, (
            f"Expected light_turn_off called 2 times, "
            f"got {graph.smart_home_service.light_turn_off.call_count}"
        )

    def test_handle_turn_off__two_entities__correct_entity_ids_used(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["light.sala", "light.quarto"]
        )
        state = _lights_state(
            output_turn_off="sala|quarto",
            available_entities={},
        )

        graph._handle_turn_off(state)

        calls = graph.smart_home_service.light_turn_off.call_args_list
        # _handle_turn_off passes entity_id as keyword arg
        used_ids = {c.kwargs.get("entity_id") or c.args[0] for c in calls}
        assert used_ids == {"light.sala", "light.quarto"}, (
            f"Expected {{'light.sala', 'light.quarto'}}, got {used_ids}"
        )


# ===========================================================================
# SmartHomeLightsGraph — _handle_change_bright
# ===========================================================================


class TestLightsChangeBrightMultipleEntities:
    """
    _handle_change_bright processes pipe-separated segments, each resolving to
    one or more entity IDs. light_turn_on must be called once per resolved
    entity with the correct brightness_pct.
    """

    def test_handle_change_bright__two_segments_one_entity_each__service_called_twice(
        self,
    ):
        graph = _make_lights_graph()
        # Side-effect: first segment → light.sala, second → light.quarto
        graph._find_entity_ids = MagicMock(
            side_effect=[["light.sala"], ["light.quarto"]]
        )
        state = _lights_state(
            output_change_bright="sala, 80|quarto, 40",
            available_entities={"sala": "light.sala", "quarto": "light.quarto"},
        )

        graph._handle_change_bright(state)

        assert graph.smart_home_service.light_turn_on.call_count == 2, (
            f"Expected 2 calls for 2 segments, "
            f"got {graph.smart_home_service.light_turn_on.call_count}"
        )

    def test_handle_change_bright__two_segments__correct_brightness_per_entity(self):
        graph = _make_lights_graph()
        graph._find_entity_ids = MagicMock(
            side_effect=[["light.sala"], ["light.quarto"]]
        )
        state = _lights_state(
            output_change_bright="sala, 80|quarto, 40",
            available_entities={},
        )

        graph._handle_change_bright(state)

        calls = graph.smart_home_service.light_turn_on.call_args_list
        commands = [
            c.kwargs.get("turn_on_command") or c.args[0] for c in calls
        ]
        by_id = {cmd.entity_id: cmd.brightness_pct for cmd in commands}

        assert by_id.get("light.sala") == 80, (
            f"light.sala expected brightness_pct=80, got {by_id.get('light.sala')}"
        )
        assert by_id.get("light.quarto") == 40, (
            f"light.quarto expected brightness_pct=40, got {by_id.get('light.quarto')}"
        )


# ===========================================================================
# SmartHomeClimateGraph — _handle_turn_on
# ===========================================================================


class TestClimateTurnOnMultipleEntities:
    """
    Verifies that _handle_turn_on calls climate_turn_on once per entity ID
    with a ClimateTurnOn command carrying the correct entity_id.
    """

    def test_handle_turn_on__two_entities__service_called_twice(self):
        graph = _make_climate_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["climate.sala", "climate.quarto"]
        )
        state = _climate_state(
            output_turn_on="ar da sala|ar do quarto",
            available_entities={},
        )

        graph._handle_turn_on(state)

        assert graph.smart_home_service.climate_turn_on.call_count == 2, (
            f"Expected climate_turn_on called 2 times, "
            f"got {graph.smart_home_service.climate_turn_on.call_count}"
        )

    def test_handle_turn_on__two_entities__correct_entity_ids_in_commands(self):
        graph = _make_climate_graph()
        graph._find_entity_ids = MagicMock(
            return_value=["climate.sala", "climate.quarto"]
        )
        state = _climate_state(
            output_turn_on="ar da sala|ar do quarto",
            available_entities={},
        )

        graph._handle_turn_on(state)

        calls = graph.smart_home_service.climate_turn_on.call_args_list
        used_ids = {
            (c.kwargs.get("command") or c.args[0]).entity_id for c in calls
        }
        assert used_ids == {"climate.sala", "climate.quarto"}, (
            f"Expected {{'climate.sala', 'climate.quarto'}}, got {used_ids}"
        )


# ===========================================================================
# SmartHomeClimateGraph — _handle_set_temperature
# ===========================================================================


class TestClimateSetTemperatureMultipleEntities:
    """
    _handle_set_temperature accepts a pipe-separated list of "device, temp"
    entries. climate_set_temperature must be called once per resolved entity
    with the correct temperature value.
    """

    def test_handle_set_temperature__two_entries__service_called_twice(self):
        graph = _make_climate_graph()
        # First entry resolves to climate.sala; second to climate.quarto.
        graph._find_entity_ids = MagicMock(
            side_effect=[["climate.sala"], ["climate.quarto"]]
        )
        state = _climate_state(
            output_set_temperature="ar da sala, 22|ar do quarto, 18",
            available_entities={},
        )

        graph._handle_set_temperature(state)

        assert graph.smart_home_service.climate_set_temperature.call_count == 2, (
            f"Expected climate_set_temperature called 2 times, "
            f"got {graph.smart_home_service.climate_set_temperature.call_count}"
        )

    def test_handle_set_temperature__two_entries__correct_temperature_per_entity(self):
        graph = _make_climate_graph()
        graph._find_entity_ids = MagicMock(
            side_effect=[["climate.sala"], ["climate.quarto"]]
        )
        state = _climate_state(
            output_set_temperature="ar da sala, 22|ar do quarto, 18",
            available_entities={},
        )

        graph._handle_set_temperature(state)

        calls = graph.smart_home_service.climate_set_temperature.call_args_list
        commands = [c.kwargs.get("command") or c.args[0] for c in calls]
        by_id = {cmd.entity_id: cmd.temperature for cmd in commands}

        assert by_id.get("climate.sala") == 22.0, (
            f"climate.sala expected temperature=22.0, got {by_id.get('climate.sala')}"
        )
        assert by_id.get("climate.quarto") == 18.0, (
            f"climate.quarto expected temperature=18.0, got {by_id.get('climate.quarto')}"
        )


# ===========================================================================
# SmartHomeClimateGraph — _handle_set_hvac_mode
# ===========================================================================


class TestClimateSetHvacModeMultipleEntities:
    """
    _handle_set_hvac_mode accepts pipe-separated "device, mode" entries.
    climate_set_hvac_mode must be called once per resolved entity with the
    correct HA mode string (after HVAC_MODE_MAP translation).
    """

    def test_handle_set_hvac_mode__two_entries__service_called_twice(self):
        graph = _make_climate_graph()
        graph._find_entity_ids = MagicMock(
            side_effect=[["climate.sala"], ["climate.quarto"]]
        )
        state = _climate_state(
            output_set_hvac_mode="ar da sala, frio|ar do quarto, calor",
            available_entities={},
        )

        graph._handle_set_hvac_mode(state)

        assert graph.smart_home_service.climate_set_hvac_mode.call_count == 2, (
            f"Expected climate_set_hvac_mode called 2 times, "
            f"got {graph.smart_home_service.climate_set_hvac_mode.call_count}"
        )

    def test_handle_set_hvac_mode__two_entries__portuguese_mode_translated_to_ha(self):
        """
        'frio' must be translated to 'cool' and 'calor' to 'heat' via HVAC_MODE_MAP
        before the command reaches the service.
        """
        graph = _make_climate_graph()
        graph._find_entity_ids = MagicMock(
            side_effect=[["climate.sala"], ["climate.quarto"]]
        )
        state = _climate_state(
            output_set_hvac_mode="ar da sala, frio|ar do quarto, calor",
            available_entities={},
        )

        graph._handle_set_hvac_mode(state)

        calls = graph.smart_home_service.climate_set_hvac_mode.call_args_list
        commands = [c.kwargs.get("command") or c.args[0] for c in calls]
        by_id = {cmd.entity_id: cmd.hvac_mode for cmd in commands}

        assert by_id.get("climate.sala") == "cool", (
            f"'frio' must translate to 'cool', got {by_id.get('climate.sala')!r}"
        )
        assert by_id.get("climate.quarto") == "heat", (
            f"'calor' must translate to 'heat', got {by_id.get('climate.quarto')!r}"
        )

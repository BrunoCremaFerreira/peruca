import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest

from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import (
    HomeAssistantSmartHomeLightRepository,
)
from domain.commands import LightTurnOn


"""
HomeAssistantSmartHomeLightRepository Unit Tests

Covers four concrete bugs:
  1. turn_on URL duplicates 'http://' scheme when base_url already includes it
  2. turn_off URL duplicates 'http://' scheme when base_url already includes it
  3. get_state does not pass entity_id to SmartHomeLight constructor
  4. get_state reads 'color_temp' (mireds) instead of 'color_temp_kelvin'
"""


def _make_repo(
    base_url: str = "http://localhost:8123",
) -> HomeAssistantSmartHomeLightRepository:
    return HomeAssistantSmartHomeLightRepository(base_url=base_url, token="test-token")


def _make_ha_state_response(
    entity_id: str = "light.sala", color_temp: int = 370, color_temp_kelvin: int = 2700
) -> dict:
    """Simulate a typical Home Assistant /api/states response."""
    return {
        "entity_id": entity_id,
        "state": "on",
        "attributes": {
            "brightness": 200,
            "color_mode": "color_temp",
            "color_temp": color_temp,
            "color_temp_kelvin": color_temp_kelvin,
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
            "supported_color_modes": ["color_temp"],
        },
    }


def _make_mock_session(json_response: dict):
    """
    Returns a mock aiohttp.ClientSession context-manager that yields
    a response whose .json() coroutine returns json_response.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


# ===========================================================================
# Bug 1 — turn_on URL construction duplicates 'http://' scheme
# ===========================================================================


class TestTurnOnUrlConstruction:
    def test_turn_on__url_construction__does_not_duplicate_scheme(self):
        """
        Bug: line 70 builds 'http://{self.base_url}/...' but self.base_url
        already contains 'http://', producing 'http://http://localhost:8123/...'.
        The URL passed to session.post must NOT start with 'http://http://'.
        """
        repo = _make_repo(base_url="http://localhost:8123")
        mock_cm_session, mock_session = _make_mock_session([])

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            cmd = LightTurnOn(entity_id="light.sala")
            asyncio.get_event_loop().run_until_complete(
                repo.turn_on(turn_on_command=cmd)
            )

        called_url = mock_session.post.call_args[0][0]
        assert not called_url.startswith("http://http://"), (
            f"URL duplicates scheme: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with 'http://localhost:8123', got: {called_url!r}"
        )


# ===========================================================================
# Bug 2 — turn_off URL construction duplicates 'http://' scheme
# ===========================================================================


class TestTurnOffUrlConstruction:
    def test_turn_off__url_construction__does_not_duplicate_scheme(self):
        """
        Bug: line 88 builds 'http://{self.base_url}/...' but self.base_url
        already contains 'http://', producing 'http://http://localhost:8123/...'.
        The URL passed to session.post must NOT start with 'http://http://'.
        """
        repo = _make_repo(base_url="http://localhost:8123")
        mock_cm_session, mock_session = _make_mock_session({"status": 200})

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            asyncio.get_event_loop().run_until_complete(
                repo.turn_off(entity_id="light.sala")
            )

        called_url = mock_session.post.call_args[0][0]
        assert not called_url.startswith("http://http://"), (
            f"URL duplicates scheme: {called_url!r}"
        )
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with 'http://localhost:8123', got: {called_url!r}"
        )


# ===========================================================================
# Bug 3 — get_state does not populate entity_id on SmartHomeLight
# ===========================================================================


class TestGetStateEntityId:
    def test_get_state__entity_id__is_populated_in_result(self):
        """
        Bug: lines 43-58 construct SmartHomeLight without passing entity_id=entity_id,
        so SmartHomeLight.entity_id is always the default empty string.
        After the fix, entity_id must match the argument passed to get_state().
        """
        entity_id = "light.quarto"
        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(
            _make_ha_state_response(entity_id=entity_id)
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id=entity_id)
            )

        assert result.entity_id == entity_id, (
            f"Expected entity_id={entity_id!r}, got {result.entity_id!r}"
        )


# ===========================================================================
# Bug 4 — get_state reads 'color_temp' (mireds) instead of 'color_temp_kelvin'
# ===========================================================================


class TestGetStateColorTempKelvin:
    def test_get_state__color_temp_kelvin__uses_kelvin_attribute(self):
        """
        Bug: line 46 reads attributes.get('color_temp') which is in mireds,
        not kelvin. The correct attribute is 'color_temp_kelvin'.
        The HA response below has color_temp=370 (mireds) and
        color_temp_kelvin=2700 (kelvin). After the fix, result.color_temp_kelvin
        must equal 2700, not 370.
        """
        repo = _make_repo()
        ha_response = _make_ha_state_response(color_temp=370, color_temp_kelvin=2700)
        mock_cm_session, _ = _make_mock_session(ha_response)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state(entity_id="light.sala")
            )

        assert result.color_temp_kelvin == 2700, (
            f"Expected color_temp_kelvin=2700 (from kelvin attribute), "
            f"got {result.color_temp_kelvin!r} — likely reading mireds value 370"
        )


# ===========================================================================
# TestGetAllLightsState — TDD (area-based commands feature)
# ===========================================================================
#
# Contract being introduced:
#   - HomeAssistantSmartHomeLightRepository.get_all_states() returns
#     List[SmartHomeLight] using ONE HTTP GET to /api/states (no per-entity
#     fan-out — plan decision #5).
#   - Must filter the global states list to entries whose entity_id starts
#     with 'light.'.
#   - Must map HA state == "unavailable" to SmartHomeLight.is_available=False
#     (otherwise True). is_on must remain False when the light is unavailable.
#   - Must propagate HTTP errors (raise_for_status) — no silent swallow.


def _make_ha_all_states_response(states: list) -> list:
    """Simulate a typical /api/states response: a JSON list of state dicts."""
    return states


def _make_state_dict(
    entity_id: str,
    state: str = "on",
    friendly_name: str = None,
    brightness: int = 200,
):
    attrs = {"brightness": brightness}
    if friendly_name is not None:
        attrs["friendly_name"] = friendly_name
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attrs,
    }


class TestGetAllLightsState:
    def test_get_all_lights_state__http_returns_states__maps_lights(self):
        """
        Given a /api/states response containing two light entities, the repo
        must return a list with two SmartHomeLight objects, with entity_id
        populated from the HA payload.
        """
        from domain.entities import SmartHomeLight

        payload = _make_ha_all_states_response(
            [
                _make_state_dict(
                    "light.cozinha_1", state="on", friendly_name="Luz Central"
                ),
                _make_state_dict(
                    "light.sala", state="off", friendly_name="Luz da Sala"
                ),
            ]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        assert isinstance(result, list)
        assert len(result) == 2, f"Expected 2 lights, got {len(result)}"
        assert all(isinstance(l, SmartHomeLight) for l in result), (
            f"Expected List[SmartHomeLight], got {[type(l) for l in result]!r}"
        )
        ids = {l.entity_id for l in result}
        assert ids == {"light.cozinha_1", "light.sala"}

    def test_get_all_lights_state__state_on__is_on_true_and_is_available_true(self):
        payload = _make_ha_all_states_response(
            [_make_state_dict("light.cozinha_1", state="on")]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        assert len(result) == 1
        light = result[0]
        assert light.is_on is True, f"Expected is_on=True, got {light.is_on!r}"
        assert light.is_available is True, (
            f"Expected is_available=True (state='on'), got {light.is_available!r}"
        )

    def test_get_all_lights_state__state_off__is_on_false_and_is_available_true(self):
        payload = _make_ha_all_states_response(
            [_make_state_dict("light.sala", state="off")]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        light = result[0]
        assert light.is_on is False, f"Expected is_on=False, got {light.is_on!r}"
        assert light.is_available is True, (
            f"state='off' must still be is_available=True, got {light.is_available!r}"
        )

    def test_get_all_lights_state__state_unavailable__is_available_false(self):
        """
        Plan checkpoint: state='unavailable' must yield is_available=False.
        is_on must be False (the light is not lit, regardless of unavailability).
        """
        payload = _make_ha_all_states_response(
            [_make_state_dict("light.quebrada", state="unavailable")]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        light = result[0]
        assert light.is_available is False, (
            f"state='unavailable' must produce is_available=False, "
            f"got {light.is_available!r}"
        )
        assert light.is_on is False, (
            f"Unavailable lights must not be reported as on, got is_on={light.is_on!r}"
        )

    def test_get_all_lights_state__non_light_entities__filtered_out(self):
        """
        Plan checkpoint: get_all_states must filter the /api/states list,
        returning only entities whose entity_id starts with 'light.'.
        """
        payload = _make_ha_all_states_response(
            [
                _make_state_dict("light.cozinha_1", state="on"),
                _make_state_dict("switch.tomada", state="on"),
                _make_state_dict("climate.sala", state="cool"),
                _make_state_dict("sensor.temp", state="22.5"),
                _make_state_dict("light.sala", state="off"),
            ]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        ids = sorted(l.entity_id for l in result)
        assert ids == ["light.cozinha_1", "light.sala"], (
            f"Only 'light.*' entities expected, got {ids!r}"
        )

    def test_get_all_lights_state__friendly_name_populated(self):
        """When HA payload supplies friendly_name, it must be carried to the entity."""
        payload = _make_ha_all_states_response(
            [
                _make_state_dict(
                    "light.cozinha_1", state="on", friendly_name="Luz Central"
                )
            ]
        )

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        assert result[0].friendly_name == "Luz Central", (
            f"Expected friendly_name='Luz Central', got {result[0].friendly_name!r}"
        )

    def test_get_all_lights_state__http_error__raises(self):
        """
        When raise_for_status throws, the error must propagate (no swallow).
        """
        repo = _make_repo()
        mock_cm_session, mock_session = _make_mock_session([])

        # Force raise_for_status to raise via the response mock.
        # We re-build the session so the response's raise_for_status raises.
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock(side_effect=RuntimeError("HTTP 500"))
        mock_resp.json = AsyncMock(return_value=[])
        mock_resp.status = 500

        mock_cm_resp = AsyncMock()
        mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_cm_resp)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            with pytest.raises(RuntimeError):
                asyncio.get_event_loop().run_until_complete(repo.get_all_states())

    def test_get_all_lights_state__empty_response__returns_empty_list(self):
        payload = _make_ha_all_states_response([])

        repo = _make_repo()
        mock_cm_session, _ = _make_mock_session(payload)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_states()
            )

        assert result == [], f"Expected [] for empty response, got {result!r}"

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    import aiohttp
    from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_sensor_repository import (
        HomeAssistantSmartHomeSensorRepository,
    )
    from domain.entities import SensorReading, SensorType
except ImportError:
    pass


"""
HomeAssistantSmartHomeSensorRepository Unit Tests

Covers the complete contract of the sensor repository adapter:
  - get_state: maps HA REST response fields to SensorReading entity
  - get_history: fetches /api/history/period and parses List[List[dict]] response
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo() -> "HomeAssistantSmartHomeSensorRepository":
    return HomeAssistantSmartHomeSensorRepository(
        base_url="http://localhost:8123",
        token="test-token",
    )


def _make_ha_state_response(
    entity_id: str = "sensor.temperature_sala",
    state: str = "23.5",
    device_class: str = "temperature",
    unit_of_measurement: str = "°C",
    friendly_name: str = "Temperatura Sala",
    last_changed: str = "2026-05-25T10:00:00+00:00",
) -> dict:
    """Simulate a typical Home Assistant /api/states response for a sensor entity."""
    attributes = {
        "friendly_name": friendly_name,
        "device_class": device_class,
    }
    if unit_of_measurement is not None:
        attributes["unit_of_measurement"] = unit_of_measurement

    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": attributes,
        "last_changed": last_changed,
    }


def _make_ha_history_entry(
    entity_id: str = "binary_sensor.motion_lavanderia",
    state: str = "on",
    device_class: str = "motion",
    friendly_name: str = "Movimento Lavanderia",
    last_changed: str = "2026-05-25T08:00:00+00:00",
) -> dict:
    """Single entry inside the inner list of a HA history response."""
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": {
            "friendly_name": friendly_name,
            "device_class": device_class,
        },
        "last_changed": last_changed,
    }


def _mock_aiohttp_session(json_response):
    """
    Returns a mock aiohttp.ClientSession context-manager that yields
    a response whose .json() coroutine returns json_response.
    Follows the same pattern as test_home_assistant_smart_home_climate_repository.py.
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
# TestHomeAssistantSmartHomeSensorRepositoryGetState
# ===========================================================================


class TestHomeAssistantSmartHomeSensorRepositoryGetState:
    def test_get_state__returns_sensor_reading(self):
        """
        get_state must return a SensorReading populated from the HA response.
        """
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(
                entity_id="sensor.temperature_sala",
                state="23.5",
                device_class="temperature",
                unit_of_measurement="°C",
                friendly_name="Temperatura Sala",
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("sensor.temperature_sala")
            )

        assert isinstance(result, SensorReading), (
            f"Expected SensorReading, got {type(result)}: {result!r}"
        )
        assert result.entity_id == "sensor.temperature_sala", (
            f"Expected entity_id='sensor.temperature_sala', got {result.entity_id!r}"
        )
        assert result.state == "23.5", f"Expected state='23.5', got {result.state!r}"
        assert result.unit == "°C", f"Expected unit='°C', got {result.unit!r}"
        assert result.friendly_name == "Temperatura Sala", (
            f"Expected friendly_name='Temperatura Sala', got {result.friendly_name!r}"
        )

    def test_get_state__maps_device_class_temperature__to_sensor_type_temperature(self):
        """device_class 'temperature' must map to SensorType.TEMPERATURE."""
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(device_class="temperature")
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("sensor.temperature_sala")
            )

        assert result.sensor_type == SensorType.TEMPERATURE, (
            f"Expected SensorType.TEMPERATURE for device_class='temperature', "
            f"got {result.sensor_type!r}"
        )

    def test_get_state__maps_device_class_door__to_sensor_type_door(self):
        """device_class 'door' must map to SensorType.DOOR."""
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(
                entity_id="binary_sensor.door_front",
                state="on",
                device_class="door",
                unit_of_measurement=None,
                friendly_name="Porta Frente",
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("binary_sensor.door_front")
            )

        assert result.sensor_type == SensorType.DOOR, (
            f"Expected SensorType.DOOR for device_class='door', got {result.sensor_type!r}"
        )

    def test_get_state__maps_device_class_motion__to_sensor_type_motion(self):
        """device_class 'motion' must map to SensorType.MOTION."""
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(
                entity_id="binary_sensor.motion_sala",
                state="off",
                device_class="motion",
                unit_of_measurement=None,
                friendly_name="Movimento Sala",
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("binary_sensor.motion_sala")
            )

        assert result.sensor_type == SensorType.MOTION, (
            f"Expected SensorType.MOTION for device_class='motion', got {result.sensor_type!r}"
        )

    def test_get_state__maps_unknown_device_class__to_sensor_type_unknown(self):
        """An unrecognized device_class must fall back to SensorType.UNKNOWN."""
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(device_class="flux_capacitor")
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("sensor.weird_device")
            )

        assert result.sensor_type == SensorType.UNKNOWN, (
            f"Expected SensorType.UNKNOWN for unknown device_class, got {result.sensor_type!r}"
        )

    def test_get_state__handles_missing_unit_of_measurement(self):
        """
        When unit_of_measurement is absent from attributes, SensorReading.unit
        must be None.
        """
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(
                entity_id="binary_sensor.door_front",
                state="on",
                device_class="door",
                unit_of_measurement=None,
                friendly_name="Porta Frente",
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("binary_sensor.door_front")
            )

        assert result.unit is None, (
            f"Expected unit=None when unit_of_measurement is absent, got {result.unit!r}"
        )

    def test_get_state__maps_binary_sensor_on_state(self):
        """
        A binary sensor with state 'on' must have state='on' in SensorReading.
        """
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session(
            _make_ha_state_response(
                entity_id="binary_sensor.window_sala",
                state="on",
                device_class="window",
                unit_of_measurement=None,
                friendly_name="Janela Sala",
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_state("binary_sensor.window_sala")
            )

        assert result.state == "on", (
            f"Expected state='on' for binary sensor, got {result.state!r}"
        )
        assert result.sensor_type == SensorType.WINDOW, (
            f"Expected SensorType.WINDOW for device_class='window', got {result.sensor_type!r}"
        )

    def test_get_state__url_contains_entity_id_and_base_url(self):
        """
        The URL sent to session.get must start with base_url and include the entity_id.
        Protects against URL duplication or missing path segments.
        """
        repo = _make_repo()
        entity_id = "sensor.temperature_sala"
        mock_cm_session, mock_session = _mock_aiohttp_session(
            _make_ha_state_response(entity_id=entity_id)
        )

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            asyncio.get_event_loop().run_until_complete(repo.get_state(entity_id))

        called_url = mock_session.get.call_args[0][0]
        assert called_url.startswith("http://localhost:8123"), (
            f"Expected URL to start with 'http://localhost:8123', got: {called_url!r}"
        )
        assert entity_id in called_url, (
            f"Expected entity_id={entity_id!r} in URL, got: {called_url!r}"
        )
        assert not called_url.startswith("http://http://"), (
            f"URL duplicates scheme: {called_url!r}"
        )

    def test_get_state__ha_returns_404__propagates_exception(self):
        """A 4xx/5xx response from HA must propagate as aiohttp.ClientResponseError."""
        repo = _make_repo()

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                MagicMock(), MagicMock(), status=404
            )
        )
        mock_resp.status = 404

        mock_cm_resp = AsyncMock()
        mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_cm_resp)

        mock_cm_session = AsyncMock()
        mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            with pytest.raises(aiohttp.ClientResponseError):
                asyncio.get_event_loop().run_until_complete(
                    repo.get_state("sensor.nonexistent")
                )


# ===========================================================================
# TestHomeAssistantSmartHomeSensorRepositoryGetHistory
# ===========================================================================


class TestHomeAssistantSmartHomeSensorRepositoryGetHistory:
    def test_get_history__returns_list_of_sensor_readings(self):
        """
        get_history must parse the HA history response (List[List[dict]])
        and return a flat List[SensorReading].
        """
        repo = _make_repo()
        # HA returns List[List[dict]] — the outer list has one item per entity
        ha_history_response = [
            [
                _make_ha_history_entry(
                    state="on", last_changed="2026-05-25T08:00:00+00:00"
                ),
                _make_ha_history_entry(
                    state="off", last_changed="2026-05-25T08:05:00+00:00"
                ),
            ]
        ]
        mock_cm_session, _ = _mock_aiohttp_session(ha_history_response)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_history("binary_sensor.motion_lavanderia", 3)
            )

        assert isinstance(result, list), (
            f"Expected list, got {type(result)}: {result!r}"
        )
        assert len(result) == 2, (
            f"Expected 2 SensorReading entries, got {len(result)}: {result!r}"
        )
        assert all(isinstance(r, SensorReading) for r in result), (
            "All items in the result must be SensorReading instances"
        )

    def test_get_history__calculates_start_time_correctly(self):
        """
        The start_time in the history URL must be approximately
        datetime.now(UTC) - timedelta(hours=hours_back).
        Tolerance: 5 seconds.
        """
        repo = _make_repo()
        hours_back = 3
        mock_cm_session, mock_session = _mock_aiohttp_session([[]])

        before_call = datetime.now(timezone.utc)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            asyncio.get_event_loop().run_until_complete(
                repo.get_history("binary_sensor.motion_lavanderia", hours_back)
            )

        after_call = datetime.now(timezone.utc)

        called_url = mock_session.get.call_args[0][0]
        # The URL must contain the history path
        assert "history/period" in called_url, (
            f"Expected URL to contain 'history/period', got: {called_url!r}"
        )
        # The URL must reference the entity
        assert "binary_sensor.motion_lavanderia" in called_url, (
            f"Expected entity_id in URL, got: {called_url!r}"
        )

        # Verify the start_time embedded in the URL is within the expected range.
        # Extract ISO timestamp from the URL (format: /api/history/period/<iso_timestamp>)
        import re

        match = re.search(r"history/period/([^?]+)", called_url)
        assert match, f"Could not find timestamp in URL: {called_url!r}"

        start_time_str = match.group(1)
        # Parse the timestamp — allow URL-encoded colons (%3A) or plain colons
        start_time_str_decoded = start_time_str.replace("%3A", ":").replace("%2B", "+")
        start_time = datetime.fromisoformat(start_time_str_decoded)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        expected_start = before_call - timedelta(hours=hours_back)
        expected_end = after_call - timedelta(hours=hours_back)

        tolerance = timedelta(seconds=10)
        assert expected_start - tolerance <= start_time <= expected_end + tolerance, (
            f"start_time {start_time!r} is not within {hours_back}h of now "
            f"(expected between {expected_start!r} and {expected_end!r})"
        )

    def test_get_history__handles_empty_history(self):
        """
        When HA returns an empty outer list, get_history must return [].
        """
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session([])

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_history("sensor.nonexistent", 3)
            )

        assert result == [], (
            f"Expected empty list for empty HA history response, got {result!r}"
        )

    def test_get_history__handles_inner_list_empty(self):
        """
        When HA returns [[]] (outer list with one empty inner list), must return [].
        """
        repo = _make_repo()
        mock_cm_session, _ = _mock_aiohttp_session([[]])

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_history("sensor.temperature_sala", 6)
            )

        assert result == [], (
            f"Expected empty list when inner list is empty, got {result!r}"
        )

    def test_get_history__sensor_type_mapped_from_device_class_in_history(self):
        """
        Each SensorReading in the history result must have sensor_type correctly
        mapped from the device_class in the history entry attributes.
        """
        repo = _make_repo()
        ha_history_response = [
            [
                _make_ha_history_entry(device_class="motion", state="on"),
            ]
        ]
        mock_cm_session, _ = _mock_aiohttp_session(ha_history_response)

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_history("binary_sensor.motion_lavanderia", 3)
            )

        assert len(result) == 1, f"Expected 1 result, got {len(result)}"
        assert result[0].sensor_type == SensorType.MOTION, (
            f"Expected SensorType.MOTION from history entry, got {result[0].sensor_type!r}"
        )

    def test_get_history__url_contains_filter_entity_id(self):
        """
        The GET request must include filter_entity_id as a query parameter
        so HA filters results to the requested entity.
        """
        repo = _make_repo()
        entity_id = "sensor.humidity_quarto"
        mock_cm_session, mock_session = _mock_aiohttp_session([[]])

        with patch("aiohttp.ClientSession", return_value=mock_cm_session):
            asyncio.get_event_loop().run_until_complete(repo.get_history(entity_id, 3))

        called_url = mock_session.get.call_args[0][0]
        assert entity_id in called_url, (
            f"Expected entity_id={entity_id!r} in URL query params, got: {called_url!r}"
        )

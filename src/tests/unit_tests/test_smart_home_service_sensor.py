import asyncio
from unittest.mock import AsyncMock, MagicMock

try:
    from domain.entities import SensorReading, SensorType
    from domain.interfaces.smart_home_repository import SmartHomeSensorRepository
    from domain.services.smart_home_service import SmartHomeService
except ImportError:
    pass


"""
SmartHomeService — sensor_get_state / sensor_get_history Unit Tests

These tests are written BEFORE the implementation exists (TDD).
They will fail with ImportError or AttributeError until the implementation lands.
"""


def _make_service():
    """
    Build a SmartHomeService with all repositories mocked.

    Returns: (service, light_repo, config_repo, alias_repo, climate_repo, sensor_repo)
    """
    light_repo = AsyncMock()
    config_repo = AsyncMock()
    config_repo.get_all_exposed_entities_ids.return_value = []
    config_repo.get_aliases_by_entity_id.return_value = []
    alias_repo = MagicMock()
    climate_repo = AsyncMock()
    sensor_repo = AsyncMock(spec=SmartHomeSensorRepository)

    service = SmartHomeService(
        smart_home_light_repository=light_repo,
        smart_home_configuration_repository=config_repo,
        smart_home_entity_alias_repository=alias_repo,
        smart_home_climate_repository=climate_repo,
        smart_home_sensor_repository=sensor_repo,
    )
    return service, light_repo, config_repo, alias_repo, climate_repo, sensor_repo


def _sample_sensor_reading() -> "SensorReading":
    """Return a pre-built SensorReading for use in assertions."""
    return SensorReading(
        entity_id="sensor.temperature_sala",
        sensor_type=SensorType.TEMPERATURE,
        state="23.5",
        unit="°C",
        friendly_name="Temperatura Sala",
    )


# ===========================================================================
# TestSmartHomeServiceSensorGetState
# ===========================================================================


class TestSmartHomeServiceSensorGetState:
    def test_sensor_get_state__delegates_to_repository(self):
        """
        sensor_get_state must forward the entity_id to sensor_repo.get_state
        and return whatever the repository returns.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        expected = _sample_sensor_reading()
        sensor_repo.get_state.return_value = expected

        # Act
        result = asyncio.get_event_loop().run_until_complete(
            service.sensor_get_state("sensor.temperature_sala")
        )

        # Assert
        sensor_repo.get_state.assert_awaited_once_with("sensor.temperature_sala")
        assert result is expected, (
            f"Expected the exact SensorReading returned by repository, got {result!r}"
        )

    def test_sensor_get_state__returns_sensor_reading(self):
        """
        The return value of sensor_get_state must be an instance of SensorReading.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        sensor_repo.get_state.return_value = _sample_sensor_reading()

        # Act
        result = asyncio.get_event_loop().run_until_complete(
            service.sensor_get_state("sensor.temperature_sala")
        )

        # Assert
        assert isinstance(result, SensorReading), (
            f"Expected SensorReading, got {type(result)}: {result!r}"
        )

    def test_sensor_get_state__passes_entity_id_unchanged(self):
        """
        The entity_id string must be forwarded to the repository without mutation.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        sensor_repo.get_state.return_value = _sample_sensor_reading()
        entity_id = "binary_sensor.door_front"

        # Act
        asyncio.get_event_loop().run_until_complete(service.sensor_get_state(entity_id))

        # Assert
        called_with = sensor_repo.get_state.call_args[0][0]
        assert called_with == entity_id, (
            f"Expected entity_id={entity_id!r} forwarded unchanged, got {called_with!r}"
        )


# ===========================================================================
# TestSmartHomeServiceSensorGetHistory
# ===========================================================================


class TestSmartHomeServiceSensorGetHistory:
    def test_sensor_get_history__delegates_to_repository(self):
        """
        sensor_get_history must forward entity_id and hours_back to
        sensor_repo.get_history and return whatever the repository returns.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        expected = [_sample_sensor_reading()]
        sensor_repo.get_history.return_value = expected

        # Act
        result = asyncio.get_event_loop().run_until_complete(
            service.sensor_get_history("binary_sensor.motion_1", 3)
        )

        # Assert
        sensor_repo.get_history.assert_awaited_once_with("binary_sensor.motion_1", 3)
        assert result is expected, (
            f"Expected the exact list returned by repository, got {result!r}"
        )

    def test_sensor_get_history__returns_list(self):
        """
        The return value of sensor_get_history must be a list.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        sensor_repo.get_history.return_value = [_sample_sensor_reading()]

        # Act
        result = asyncio.get_event_loop().run_until_complete(
            service.sensor_get_history("sensor.humidity_quarto", 6)
        )

        # Assert
        assert isinstance(result, list), (
            f"Expected list, got {type(result)}: {result!r}"
        )

    def test_sensor_get_history__passes_hours_back_unchanged(self):
        """
        The hours_back value must be forwarded to the repository without mutation.
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        sensor_repo.get_history.return_value = []
        hours_back = 12

        # Act
        asyncio.get_event_loop().run_until_complete(
            service.sensor_get_history("sensor.temperature_sala", hours_back)
        )

        # Assert
        call_args = sensor_repo.get_history.call_args
        passed_hours = (
            call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("hours_back")
        )
        assert passed_hours == hours_back, (
            f"Expected hours_back={hours_back} forwarded unchanged, got {passed_hours!r}"
        )

    def test_sensor_get_history__empty_history__returns_empty_list(self):
        """
        When the repository returns an empty list, sensor_get_history must return [].
        """
        # Arrange
        service, _, _, _, _, sensor_repo = _make_service()
        sensor_repo.get_history.return_value = []

        # Act
        result = asyncio.get_event_loop().run_until_complete(
            service.sensor_get_history("sensor.smoke_detector", 24)
        )

        # Assert
        assert result == [], f"Expected empty list, got {result!r}"

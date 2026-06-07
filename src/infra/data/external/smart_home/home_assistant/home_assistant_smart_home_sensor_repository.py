import aiohttp
from datetime import datetime, timedelta, timezone
from typing import List

from domain.entities import SensorReading, SensorType
from domain.interfaces.smart_home_repository import SmartHomeSensorRepository


_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(connect=5, total=30)


DEVICE_CLASS_TO_SENSOR_TYPE = {
    "temperature": SensorType.TEMPERATURE,
    "door": SensorType.DOOR,
    "window": SensorType.WINDOW,
    "motion": SensorType.MOTION,
    "presence": SensorType.PRESENCE,
    "humidity": SensorType.HUMIDITY,
    "smoke": SensorType.SMOKE,
    "illuminance": SensorType.ILLUMINANCE,
}


class HomeAssistantSmartHomeSensorRepository(SmartHomeSensorRepository):
    """
    Implementation of SmartHomeSensorRepository for Home Assistant using the REST API.
    """

    def __init__(self, base_url: str, token: str):
        """
        Args:
            base_url: Base URL of the Home Assistant instance (e.g., 'http://localhost:8123').
            token: Long-lived access token for authentication.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._ssl = False if self.base_url.startswith("https") else None
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=self.headers, timeout=_DEFAULT_TIMEOUT
            )
        return self._session

    def _map_sensor_type(self, device_class: str) -> SensorType:
        return DEVICE_CLASS_TO_SENSOR_TYPE.get(device_class, SensorType.UNKNOWN)

    def _parse_last_changed(self, raw: str) -> datetime:
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)

    async def get_state(self, entity_id: str) -> SensorReading:
        """
        Fetches the current state and attributes of a sensor entity from Home Assistant.

        Args:
            entity_id: The entity ID of the sensor.

        Returns:
            SensorReading instance populated with the current state.
        """
        url = f"{self.base_url}/api/states/{entity_id}"
        session = self._get_session()
        async with session.get(url, headers=self.headers, ssl=self._ssl) as resp:
            resp.raise_for_status()
            data = await resp.json()

        attributes = data.get("attributes", {})
        device_class = attributes.get("device_class", "")
        return SensorReading(
            entity_id=entity_id,
            sensor_type=self._map_sensor_type(device_class),
            state=data["state"],
            unit=attributes.get("unit_of_measurement"),
            friendly_name=attributes.get("friendly_name"),
            last_changed=self._parse_last_changed(data.get("last_changed", "")),
        )

    async def get_history(self, entity_id: str, hours_back: int) -> List[SensorReading]:
        """
        Fetches historical states of a sensor entity from Home Assistant.

        Args:
            entity_id: The entity ID of the sensor.
            hours_back: Number of hours of history to retrieve.

        Returns:
            List of SensorReading instances ordered by time.
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        start_time_str = start_time.isoformat()
        url = (
            f"{self.base_url}/api/history/period/{start_time_str}"
            f"?filter_entity_id={entity_id}&end_time={end_time.isoformat()}"
        )

        session = self._get_session()
        async with session.get(url, headers=self.headers, ssl=self._ssl) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if not data or not data[0]:
            return []

        readings: List[SensorReading] = []
        for entry in data[0]:
            attributes = entry.get("attributes", {})
            device_class = attributes.get("device_class", "")
            readings.append(
                SensorReading(
                    entity_id=entry.get("entity_id", entity_id),
                    sensor_type=self._map_sensor_type(device_class),
                    state=entry["state"],
                    unit=attributes.get("unit_of_measurement"),
                    friendly_name=attributes.get("friendly_name"),
                    last_changed=self._parse_last_changed(
                        entry.get("last_changed", "")
                    ),
                )
            )

        return readings

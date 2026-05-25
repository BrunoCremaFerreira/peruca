import aiohttp
from domain.commands import ClimateSetTemperature, ClimateSetHvacMode, ClimateTurnOn, ClimateTurnOff
from domain.entities import SmartHomeClimate, SmartHomeHvacMode
from domain.interfaces.smart_home_repository import SmartHomeClimateRepository


class HomeAssistantSmartHomeClimateRepository(SmartHomeClimateRepository):
    """
    Implementation of SmartHomeClimateRepository for Home Assistant using the REST API.
    """

    def __init__(self, base_url: str, token: str):
        """
        Args:
            base_url: Base URL of the Home Assistant instance (e.g., 'http://localhost:8123').
            token: Long-lived access token for authentication.
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def get_state(self, entity_id: str) -> SmartHomeClimate:
        """
        Fetches the current state and attributes of a climate entity from Home Assistant.

        Args:
            entity_id: The entity ID of the climate device.

        Returns:
            SmartHomeClimate instance populated with the current state.
        """
        url = f"{self.base_url}/api/states/{entity_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

        attributes = data.get("attributes", {})
        state = data["state"]
        return SmartHomeClimate(
            entity_id=entity_id,
            hvac_mode=SmartHomeHvacMode(state),
            is_on=state != "off",
            target_temperature=attributes.get("temperature"),
            current_temperature=attributes.get("current_temperature"),
            hvac_modes=attributes.get("hvac_modes", []),
            fan_mode=attributes.get("fan_mode"),
            swing_mode=attributes.get("swing_mode"),
        )

    async def set_temperature(self, command: ClimateSetTemperature) -> dict:
        """
        Sends a request to Home Assistant to set the target temperature of a climate entity.

        Args:
            command: ClimateSetTemperature command containing entity_id and temperature.

        Returns:
            Dictionary with Home Assistant response.
        """
        url = f"{self.base_url}/api/services/climate/set_temperature"
        payload = {
            "entity_id": command.entity_id,
            "temperature": command.temperature,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def set_hvac_mode(self, command: ClimateSetHvacMode) -> dict:
        """
        Sends a request to Home Assistant to set the HVAC mode of a climate entity.

        Args:
            command: ClimateSetHvacMode command containing entity_id and hvac_mode string.

        Returns:
            Dictionary with Home Assistant response.
        """
        url = f"{self.base_url}/api/services/climate/set_hvac_mode"
        payload = {
            "entity_id": command.entity_id,
            "hvac_mode": command.hvac_mode,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def turn_on(self, command: ClimateTurnOn) -> dict:
        """
        Sends a request to Home Assistant to turn on a climate entity.

        Args:
            command: ClimateTurnOn command containing entity_id.

        Returns:
            Dictionary with Home Assistant response.
        """
        url = f"{self.base_url}/api/services/climate/turn_on"
        payload = {"entity_id": command.entity_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def turn_off(self, command: ClimateTurnOff) -> dict:
        """
        Sends a request to Home Assistant to turn off a climate entity.

        Args:
            command: ClimateTurnOff command containing entity_id.

        Returns:
            Dictionary with Home Assistant response, or a fallback dict if the
            response body is not JSON.
        """
        url = f"{self.base_url}/api/services/climate/turn_off"
        payload = {"entity_id": command.entity_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return {"status": resp.status, "message": "Request successful"}

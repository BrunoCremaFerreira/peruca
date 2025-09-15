from dataclasses import asdict
import aiohttp
from domain.commands import LightTurnOn
from domain.entities import SmartHomeLight
from domain.interfaces.smart_home_repository import SmartHomeLightRepository


class HomeAssistantSmartHomeLightRepository(SmartHomeLightRepository):
    """
    Implementation of SmartHomeLightRepository for Home Assistant using the REST API.
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
            "Content-Type": "application/json"
        }

    async def get_state(self, entity_id: str) -> 'SmartHomeLight':
        """
        Fetches the current state and attributes of a light from Home Assistant.

        Args:
            entity_id: The entity ID of the light.

        Returns:
            SmartHomeLight instance populated with the current state.
        """
        url = f"{self.base_url}/api/states/{entity_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

        attributes = data.get("attributes", {})
        return SmartHomeLight(
            brightness=attributes.get("brightness"),
            color_mode=attributes.get("color_mode"),
            color_temp_kelvin=attributes.get("color_temp"),
            effect=attributes.get("effect"),
            effect_list=attributes.get("effect_list", []),
            hs_color=attributes.get("hs_color"),
            is_on=data.get("state") == "on",
            max_color_temp_kelvin=attributes.get("max_color_temp_kelvin"),
            min_color_temp_kelvin=attributes.get("min_color_temp_kelvin"),
            rgb_color=attributes.get("rgb_color"),
            rgbw_color=attributes.get("rgbw_color"),
            rgbww_color=attributes.get("rgbww_color"),
            supported_color_modes=attributes.get("supported_color_modes", []),
            xy_color=attributes.get("xy_color")
        )

    async def turn_on(self, turn_on_command: 'LightTurnOn') -> dict:
        """
        Sends a request to Home Assistant to turn on a light with specified parameters.

        Args:
            turn_on_command: LightTurnOn dataclass instance containing desired parameters.

        Returns:
            Dictionary with Home Assistant response.
        """
        url = f"{self.base_url}/api/services/light/turn_on"
        payload = {k: v for k, v in asdict(turn_on_command).items() if v is not None}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def turn_off(self, entity_id: str) -> dict:
        """
        Sends a request to Home Assistant to turn off a light.

        Args:
            entity_id: The entity ID of the light.

        Returns:
            Dictionary with Home Assistant response.
        """
        url = f"http://{self.base_url}/api/services/light/turn_off"
        payload = {"entity_id": entity_id}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return {"status": resp.status, "message": "Request successful"}
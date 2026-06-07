import aiohttp
from domain.entities import SmartHomeCamera, SmartHomeCameraSnapshot
from domain.interfaces.smart_home_repository import SmartHomeCameraRepository


class HomeAssistantSmartHomeCameraRepository(SmartHomeCameraRepository):
    """
    Implementation of SmartHomeCameraRepository for Home Assistant using the REST API.
    """

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def get_state(self, entity_id: str) -> SmartHomeCamera:
        session = self._get_session()
        async with session.get(
            f"{self._base_url}/api/states/{entity_id}",
            headers=self._headers,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return SmartHomeCamera(
                entity_id=entity_id,
                state=data["state"],
                friendly_name=data.get("attributes", {}).get("friendly_name"),
                is_available=data["state"] != "unavailable",
            )

    async def get_snapshot(self, entity_id: str) -> SmartHomeCameraSnapshot:
        session = self._get_session()
        async with session.get(
            f"{self._base_url}/api/camera_proxy/{entity_id}",
            headers=self._headers,
        ) as response:
            response.raise_for_status()
            image_bytes = await response.read()
            return SmartHomeCameraSnapshot(
                entity_id=entity_id,
                image_bytes=image_bytes,
            )

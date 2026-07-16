import aiohttp
from domain.entities import SmartHomeCamera, SmartHomeCameraSnapshot
from domain.interfaces.smart_home_repository import SmartHomeCameraRepository


_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(connect=5, total=30)


class HomeAssistantSmartHomeCameraRepository(SmartHomeCameraRepository):
    """
    Implementation of SmartHomeCameraRepository for Home Assistant using the REST API.
    """

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        # GET-only repository: no Content-Type header (there is no request
        # body, and the snapshot endpoint returns binary, not JSON).
        self._headers = {
            "Authorization": f"Bearer {token}",
        }
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=self._headers, timeout=_DEFAULT_TIMEOUT
            )
        return self._session

    async def get_state(self, entity_id: str) -> SmartHomeCamera:
        session = self._get_session()
        async with session.get(
            f"{self._base_url}/api/states/{entity_id}",
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
        ) as response:
            response.raise_for_status()
            image_bytes = await response.read()
            # aiohttp reports "application/octet-stream" when the header is
            # absent; only image/* values are trusted, anything else keeps the
            # entity default ("image/jpeg") so the data URI is never invalid.
            content_type = response.content_type or ""
            if content_type.startswith("image/"):
                return SmartHomeCameraSnapshot(
                    entity_id=entity_id,
                    image_bytes=image_bytes,
                    content_type=content_type,
                )
            return SmartHomeCameraSnapshot(
                entity_id=entity_id,
                image_bytes=image_bytes,
            )

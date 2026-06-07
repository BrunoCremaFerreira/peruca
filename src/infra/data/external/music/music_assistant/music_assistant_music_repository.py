from typing import List, Optional

import aiohttp

from domain.entities import MusicPlayer, MusicSearchResult
from domain.interfaces.music_repository import MusicRepository


def _extract_current_track(item: dict) -> Optional[str]:
    title = item.get("current_media", {}).get("title")
    if title:
        return title
    name = item.get("queue_item", {}).get("name")
    if name:
        return name
    return item.get("current_track")


def _extract_artist(item: dict) -> Optional[str]:
    artists = item.get("artists", [])
    if artists:
        first = artists[0]
        if isinstance(first, dict):
            return first.get("name", "")
        return str(first)
    return item.get("artist") or None


class MusicAssistantMusicRepository(MusicRepository):
    """
    HTTP adapter for the Music Assistant 2.x REST API.
    """

    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._headers())
        return self._session

    async def get_players(self) -> List[MusicPlayer]:
        url = f"{self.base_url}/api/players"
        session = self._get_session()
        async with session.get(url, headers=self._headers()) as resp:
            resp.raise_for_status()
            data = await resp.json()

        players: List[MusicPlayer] = []
        for item in data or []:
            players.append(
                MusicPlayer(
                    player_id=item.get("player_id", ""),
                    name=item.get("display_name", item.get("name", "")),
                    state=item.get("state", "idle"),
                    volume_level=item.get("volume_level"),
                    current_track=_extract_current_track(item),
                )
            )
        return players

    async def search(self, query: str, limit: int = 5) -> List[MusicSearchResult]:
        url = f"{self.base_url}/api/search"
        params = {
            "query": query,
            "media_types": "track,artist,playlist,album",
            "limit": limit,
        }
        session = self._get_session()
        async with session.get(url, headers=self._headers(), params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        results: List[MusicSearchResult] = []
        # Music Assistant returns a dict of media_type -> list
        if isinstance(data, dict):
            for _media_type, items in data.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    results.append(
                        MusicSearchResult(
                            media_id=item.get("item_id", item.get("media_id", "")),
                            media_type=item.get("media_type", _media_type.rstrip("s")),
                            name=item.get("name", ""),
                            artist=_extract_artist(item),
                        )
                    )
        elif isinstance(data, list):
            for item in data:
                results.append(
                    MusicSearchResult(
                        media_id=item.get("item_id", item.get("media_id", "")),
                        media_type=item.get("media_type", "track"),
                        name=item.get("name", ""),
                        artist=_extract_artist(item),
                    )
                )
        return results

    async def play_media(
        self, player_id: str, media_id: str, media_type: str
    ) -> dict:
        url = f"{self.base_url}/api/players/play_media"
        payload = {
            "player_id": player_id,
            "media_id": media_id,
            "media_type": media_type,
        }
        session = self._get_session()
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def player_command(self, player_id: str, command: str) -> dict:
        url = f"{self.base_url}/api/players/player_command"
        payload = {"player_id": player_id, "command": command}
        session = self._get_session()
        async with session.post(url, headers=self._headers(), json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def set_volume(self, player_id: str, volume: int) -> dict:
        url = f"{self.base_url}/api/players/{player_id}/volume_set/{volume}"
        session = self._get_session()
        async with session.post(url, headers=self._headers()) as resp:
            resp.raise_for_status()
            return await resp.json()

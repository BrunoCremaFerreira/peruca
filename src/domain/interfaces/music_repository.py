from abc import ABC, abstractmethod
from typing import List

from domain.entities import MusicPlayer, MusicSearchResult


class MusicRepository(ABC):
    """
    Interface for Music Assistant integration
    """

    @abstractmethod
    async def get_players(self) -> List[MusicPlayer]:
        """
        Return all available media players.
        """
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> List[MusicSearchResult]:
        """
        Search for media matching the given query.
        """
        pass

    @abstractmethod
    async def play_media(
        self, player_id: str, media_id: str, media_type: str
    ) -> dict:
        """
        Play a media item on the specified player.
        """
        pass

    @abstractmethod
    async def player_command(self, player_id: str, command: str) -> dict:
        """
        Send a transport command (play, pause, next, previous, stop) to a player.
        """
        pass

    @abstractmethod
    async def set_volume(self, player_id: str, volume: int) -> dict:
        """
        Set the volume (0–100) on the specified player.
        """
        pass

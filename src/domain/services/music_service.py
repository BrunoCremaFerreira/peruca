import time
from typing import List, Optional

from domain.entities import MusicPlayer, MusicSearchResult
from domain.interfaces.music_repository import MusicRepository


class MusicService:
    """
    Domain service for Music Assistant operations.
    """

    def __init__(
        self, music_repository: MusicRepository, players_cache_ttl: float = 3.0
    ) -> None:
        self._repository = music_repository
        self._players_cache_ttl = players_cache_ttl
        self._players_cache: Optional[List[MusicPlayer]] = None
        self._players_cache_at = 0.0

    async def get_players(self) -> List[MusicPlayer]:
        """Return all available media players, cached for players_cache_ttl seconds."""
        now = time.monotonic()
        if (
            self._players_cache is not None
            and now - self._players_cache_at < self._players_cache_ttl
        ):
            return self._players_cache

        players = await self._repository.get_players()
        self._players_cache = players
        self._players_cache_at = now
        return players

    async def search_and_play(
        self, query: str, media_type: str, player_id: str
    ) -> str:
        """
        Search for media matching the query and play the first result.
        Returns a descriptive string on success or failure.
        """
        results = await self._repository.search(query=query, limit=5)

        if not results:
            return f"Nenhum resultado encontrado para: {query}"

        first = results[0]
        await self._repository.play_media(
            player_id=player_id,
            media_id=first.media_id,
            media_type=first.media_type,
        )
        return f"Tocando: {first.name}"

    async def send_player_command(self, player_id: str, command: str) -> str:
        """Send a transport command to a player and return a status string."""
        await self._repository.player_command(player_id=player_id, command=command)
        return f"Comando '{command}' enviado para {player_id}"

    async def set_volume(self, player_id: str, volume: int) -> str:
        """Set the player volume, clipping to the valid 0–100 range."""
        clipped = max(0, min(100, volume))
        await self._repository.set_volume(player_id=player_id, volume=clipped)
        return f"Volume definido para {clipped} em {player_id}"

    async def get_now_playing(self, player_id: str) -> str:
        """
        Return a string describing what is currently playing on the given player.
        Falls back to a 'nothing playing' message when idle/paused.
        """
        players = await self._repository.get_players()
        target = next((p for p in players if p.player_id == player_id), None)

        if target is None:
            return f"Player '{player_id}' não encontrado."

        if target.state == "playing" and target.current_track:
            return f"Tocando agora: {target.current_track}"

        return "Nenhuma música tocando no momento."

    def auto_select_player(self, players: List[MusicPlayer]) -> Optional[MusicPlayer]:
        """
        Return the single player when there is exactly one, otherwise None.
        Callers must handle the None case by asking the user to choose.
        """
        if len(players) == 1:
            return players[0]
        return None

"""
MusicService.get_players TTL-cache unit tests — Change #8 / Contract A (TDD RED).

Desired contract:
  - `MusicService.__init__` gains a `players_cache_ttl: float = 3.0` parameter.
  - `get_players()` caches the repository result for `players_cache_ttl` seconds,
    measured with `time.monotonic()`.
  - Within the TTL window, repeated calls return the cached value WITHOUT calling
    `self._repository.get_players()` again.
  - After the TTL expires, the repository is queried again and the cache is
    refreshed.

These tests are written BEFORE the implementation and are expected to FAIL today,
because `get_players()` delegates to the repository on every call (no cache).

Time is controlled by patching `time.monotonic` in the music_service module, so
the tests are deterministic. The repository is an AsyncMock — no HTTP traffic.

Pattern: asyncio.get_event_loop().run_until_complete(coro) — no pytest-asyncio.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.services.music_service import MusicService
from domain.entities import MusicPlayer


# ===========================================================================
# Helpers
# ===========================================================================


def _make_repo(players):
    repo = MagicMock()
    repo.get_players = AsyncMock(return_value=players)
    return repo


def _sample_player(player_id: str = "player.living_room") -> MusicPlayer:
    return MusicPlayer(
        player_id=player_id,
        name="Living Room",
        state="idle",
        volume_level=0.5,
        current_track=None,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# TestMusicServiceGetPlayersCache
# ===========================================================================


class TestMusicServiceGetPlayersCache:
    def test_get_players__within_ttl__hits_repository_once(self):
        """
        Two consecutive calls within the TTL window must call the repository
        exactly once; both calls must return the cached list.
        """
        players = [_sample_player()]
        repo = _make_repo(players)
        service = MusicService(music_repository=repo, players_cache_ttl=3.0)

        # Freeze the clock so both calls fall inside the TTL window.
        with patch("domain.services.music_service.time.monotonic", return_value=100.0):
            first = _run(service.get_players())
            second = _run(service.get_players())

        repo.get_players.assert_called_once()
        assert first == players
        assert second == players

    def test_get_players__after_ttl_expires__hits_repository_twice(self):
        """
        When the clock advances beyond the TTL between two calls, the repository
        must be queried again (two calls total).
        """
        players = [_sample_player()]
        repo = _make_repo(players)
        ttl = 3.0
        service = MusicService(music_repository=repo, players_cache_ttl=ttl)

        # Use a mutable return_value instead of a positional side_effect list:
        # the production code reads time.monotonic() once per call, but asyncio's
        # run_until_complete also reads the shared module clock an undefined
        # number of times. A constant-per-call return_value keeps the test
        # deterministic regardless of how often the clock is read.
        with patch(
            "domain.services.music_service.time.monotonic"
        ) as mock_clock:
            # t=100: cache miss, repository queried and result cached.
            mock_clock.return_value = 100.0
            players1 = _run(service.get_players())
            # Advance the clock past the TTL window: cache expired.
            mock_clock.return_value = 100.0 + ttl + 1
            players2 = _run(service.get_players())

        assert repo.get_players.call_count == 2
        assert players1 == players
        assert players2 == players

    def test_get_players__within_ttl__returns_value_equal_to_repository_list(self):
        """The cached value returned within TTL must equal the repository list."""
        players = [_sample_player("player.a"), _sample_player("player.b")]
        repo = _make_repo(players)
        service = MusicService(music_repository=repo, players_cache_ttl=3.0)

        with patch("domain.services.music_service.time.monotonic", return_value=50.0):
            result = _run(service.get_players())

        assert result == players


# ===========================================================================
# Regression: other methods keep working with the new constructor parameter
# ===========================================================================


class TestMusicServiceOtherMethodsStillWork:
    def test_search_and_play__still_delegates_to_repository(self):
        """
        Adding players_cache_ttl must not break search_and_play. With a single
        search result, play_media must be called with the first result.
        """
        from domain.entities import MusicSearchResult

        repo = MagicMock()
        result_item = MusicSearchResult(
            media_id="track::42",
            media_type="track",
            name="Song A",
            artist="Artist X",
        )
        repo.search = AsyncMock(return_value=[result_item])
        repo.play_media = AsyncMock(return_value={"status": "ok"})

        service = MusicService(music_repository=repo, players_cache_ttl=3.0)
        result = _run(
            service.search_and_play(
                query="Song A", media_type="track", player_id="player.living_room"
            )
        )

        repo.play_media.assert_called_once_with(
            player_id="player.living_room",
            media_id="track::42",
            media_type="track",
        )
        assert isinstance(result, str)

    def test_get_now_playing__still_returns_string(self):
        """get_now_playing must keep returning a descriptive string."""
        playing = _sample_player("player.living_room")
        playing.state = "playing"
        playing.current_track = "Bohemian Rhapsody"
        repo = _make_repo([playing])

        service = MusicService(music_repository=repo, players_cache_ttl=3.0)
        result = _run(service.get_now_playing(player_id="player.living_room"))

        assert isinstance(result, str)
        assert "Bohemian Rhapsody" in result

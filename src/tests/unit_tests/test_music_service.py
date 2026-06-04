"""
MusicService Unit Tests (TDD — RED phase)

Covers the domain service MusicService that orchestrates interactions with
MusicRepository.  All repository methods are mocked — no real HTTP traffic.

Pattern: asyncio.get_event_loop().run_until_complete(coro) — no pytest-asyncio.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from domain.services.music_service import MusicService
    from domain.entities import MusicPlayer, MusicSearchResult
except ImportError:
    pytest.skip(
        "MusicService / MusicPlayer not yet implemented — RED phase",
        allow_module_level=True,
    )


# ===========================================================================
# Helpers
# ===========================================================================


def _make_repo():
    repo = MagicMock()
    repo.get_players = AsyncMock(return_value=[])
    repo.search = AsyncMock(return_value=[])
    repo.play_media = AsyncMock(return_value={"status": "ok"})
    repo.player_command = AsyncMock(return_value={"status": "ok"})
    repo.set_volume = AsyncMock(return_value={"status": "ok"})
    return repo


def _sample_player(
    player_id: str = "player.living_room",
    name: str = "Living Room",
    state: str = "idle",
    current_track: str = None,
) -> MusicPlayer:
    return MusicPlayer(
        player_id=player_id,
        name=name,
        state=state,
        volume_level=0.5,
        current_track=current_track,
    )


def _sample_search_result(
    media_id: str = "track::1",
    media_type: str = "track",
    name: str = "Song A",
    artist: str = "Artist X",
) -> MusicSearchResult:
    return MusicSearchResult(
        media_id=media_id,
        media_type=media_type,
        name=name,
        artist=artist,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# TestMusicServiceGetPlayers
# ===========================================================================


class TestMusicServiceGetPlayers:
    def test_get_players__delegates_to_repository__returns_list(self):
        """get_players() must delegate to the repository and return its value."""
        repo = _make_repo()
        players = [_sample_player()]
        repo.get_players.return_value = players

        service = MusicService(music_repository=repo)
        result = _run(service.get_players())

        repo.get_players.assert_called_once()
        assert result == players


# ===========================================================================
# TestMusicServiceSearchAndPlay
# ===========================================================================


class TestMusicServiceSearchAndPlay:
    def test_search_and_play__found_results__calls_play_media_with_first_result(self):
        """
        Given search returns results, search_and_play must call play_media with
        the first result's media_id and media_type.
        """
        repo = _make_repo()
        result_item = _sample_search_result(media_id="track::42", media_type="track")
        repo.search.return_value = [result_item]

        service = MusicService(music_repository=repo)
        _run(
            service.search_and_play(
                query="Song A", media_type="track", player_id="player.living_room"
            )
        )

        repo.search.assert_called_once_with(query="Song A", limit=5)
        repo.play_media.assert_called_once_with(
            player_id="player.living_room",
            media_id="track::42",
            media_type="track",
        )

    def test_search_and_play__no_results__returns_error_string_not_exception(self):
        """
        When search returns an empty list, search_and_play must return a
        non-empty error string describing the situation — it must NOT raise.
        """
        repo = _make_repo()
        repo.search.return_value = []

        service = MusicService(music_repository=repo)
        result = _run(
            service.search_and_play(
                query="Unknown Song", media_type="track", player_id="player.x"
            )
        )

        repo.play_media.assert_not_called()
        assert isinstance(result, str)
        assert len(result) > 0, "Expected a non-empty error description string"

    def test_search_and_play__found_results__returns_string(self):
        """search_and_play must return a string (success message) when media is found."""
        repo = _make_repo()
        repo.search.return_value = [_sample_search_result()]

        service = MusicService(music_repository=repo)
        result = _run(
            service.search_and_play(
                query="Song A", media_type="track", player_id="player.living_room"
            )
        )

        assert isinstance(result, str)


# ===========================================================================
# TestMusicServiceSendPlayerCommand
# ===========================================================================


class TestMusicServiceSendPlayerCommand:
    def test_send_player_command__delegates_to_repository(self):
        """send_player_command must delegate to repo.player_command and return str."""
        repo = _make_repo()

        service = MusicService(music_repository=repo)
        result = _run(
            service.send_player_command(player_id="player.x", command="next")
        )

        repo.player_command.assert_called_once_with(
            player_id="player.x", command="next"
        )
        assert isinstance(result, str)


# ===========================================================================
# TestMusicServiceSetVolume
# ===========================================================================


class TestMusicServiceSetVolume:
    def test_set_volume__valid_value__delegates_to_repository(self):
        """set_volume must delegate to repo.set_volume."""
        repo = _make_repo()

        service = MusicService(music_repository=repo)
        result = _run(service.set_volume(player_id="player.x", volume=50))

        repo.set_volume.assert_called_once_with(player_id="player.x", volume=50)
        assert isinstance(result, str)

    def test_set_volume__negative_value__clips_to_zero(self):
        """
        Volume below 0 must be clipped to 0 before calling the repository.
        The repository must never receive a negative volume.
        """
        repo = _make_repo()

        service = MusicService(music_repository=repo)
        _run(service.set_volume(player_id="player.x", volume=-10))

        kwargs = repo.set_volume.call_args[1]
        args = repo.set_volume.call_args[0]
        called_volume = kwargs.get("volume") if "volume" in kwargs else args[1]
        assert called_volume == 0, (
            f"Expected volume clipped to 0, got {called_volume!r}"
        )

    def test_set_volume__above_100__clips_to_100(self):
        """
        Volume above 100 must be clipped to 100 before calling the repository.
        The repository must never receive a value greater than 100.
        """
        repo = _make_repo()

        service = MusicService(music_repository=repo)
        _run(service.set_volume(player_id="player.x", volume=150))

        called_volume = repo.set_volume.call_args[1].get(
            "volume"
        ) or repo.set_volume.call_args[0][1]
        assert called_volume == 100, (
            f"Expected volume clipped to 100, got {called_volume!r}"
        )


# ===========================================================================
# TestMusicServiceGetNowPlaying
# ===========================================================================


class TestMusicServiceGetNowPlaying:
    def test_get_now_playing__player_playing_with_track__returns_string_with_track_name(
        self,
    ):
        """
        When the target player state is 'playing' and has a current_track,
        get_now_playing must return a string that includes the track name.
        """
        repo = _make_repo()
        playing_player = _sample_player(
            player_id="player.living_room",
            state="playing",
            current_track="Bohemian Rhapsody",
        )
        repo.get_players.return_value = [playing_player]

        service = MusicService(music_repository=repo)
        result = _run(service.get_now_playing(player_id="player.living_room"))

        assert isinstance(result, str)
        assert "Bohemian Rhapsody" in result, (
            f"Expected track name in result, got: {result!r}"
        )

    def test_get_now_playing__player_idle__returns_nothing_playing_message(self):
        """
        When the target player state is 'idle', get_now_playing must return a
        string indicating nothing is playing (not an empty string or exception).
        """
        repo = _make_repo()
        idle_player = _sample_player(
            player_id="player.bedroom", state="idle", current_track=None
        )
        repo.get_players.return_value = [idle_player]

        service = MusicService(music_repository=repo)
        result = _run(service.get_now_playing(player_id="player.bedroom"))

        assert isinstance(result, str)
        assert len(result) > 0, "Expected a non-empty response for idle player"


# ===========================================================================
# TestMusicServiceAutoSelectPlayer
# ===========================================================================


class TestMusicServiceAutoSelectPlayer:
    def test_auto_select_player__single_player__returns_that_player(self):
        """When there is exactly one player, auto_select_player must return it."""
        repo = _make_repo()
        player = _sample_player()
        service = MusicService(music_repository=repo)

        result = service.auto_select_player([player])

        assert result is player

    def test_auto_select_player__multiple_players__returns_none(self):
        """
        When there are multiple players, the service cannot decide automatically
        and must return None (forcing select_player intent).
        """
        repo = _make_repo()
        players = [_sample_player("player.a"), _sample_player("player.b")]
        service = MusicService(music_repository=repo)

        result = service.auto_select_player(players)

        assert result is None, (
            f"Expected None for multiple players, got {result!r}"
        )

    def test_auto_select_player__empty_list__returns_none(self):
        """When the player list is empty, auto_select_player must return None."""
        repo = _make_repo()
        service = MusicService(music_repository=repo)

        result = service.auto_select_player([])

        assert result is None, f"Expected None for empty list, got {result!r}"

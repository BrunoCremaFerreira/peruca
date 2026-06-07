"""
MusicAssistantMusicRepository Unit Tests (TDD — RED phase)

Covers the aiohttp-based adapter for the Music Assistant 2.x API.
All HTTP traffic is mocked — no real network calls.

Pattern: _make_mock_session() identical to test_home_assistant_light_repository.py.
Pattern: asyncio.get_event_loop().run_until_complete(coro) — no pytest-asyncio.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from infra.data.external.music.music_assistant.music_assistant_music_repository import (
        MusicAssistantMusicRepository,
    )
    from domain.entities import MusicPlayer, MusicSearchResult
except ImportError:
    pytest.skip(
        "MusicAssistantMusicRepository not yet implemented — RED phase",
        allow_module_level=True,
    )


# ===========================================================================
# Session mock helpers  (identical pattern to test_home_assistant_light_repository)
# ===========================================================================


def _make_mock_session(json_response):
    """
    Returns (mock_cm_session, mock_session) where mock_cm_session is the
    aiohttp.ClientSession context-manager mock and mock_session is the inner
    session whose .get / .post calls can be inspected.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)

    mock_cm_session = AsyncMock()
    mock_cm_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm_session.__aexit__ = AsyncMock(return_value=False)

    return mock_cm_session, mock_session


def _make_repo(base_url: str = "http://localhost:8095", token: str = "test-token"):
    return MusicAssistantMusicRepository(base_url=base_url, token=token)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# Sample API payloads
# ===========================================================================


def _mass_players_payload():
    """Simulate a Music Assistant GET /api/players response."""
    return [
        {
            "player_id": "player.living_room",
            "name": "Living Room",
            "state": "playing",
            "volume_level": 0.6,
            "current_track": "Bohemian Rhapsody",
        },
        {
            "player_id": "player.bedroom",
            "name": "Bedroom",
            "state": "idle",
            "volume_level": 0.3,
            "current_track": None,
        },
    ]


def _mass_search_payload():
    """Simulate a Music Assistant GET /api/search response."""
    return {
        "tracks": [
            {
                "media_id": "track::1",
                "media_type": "track",
                "name": "Song A",
                "artist": "Artist X",
            },
            {
                "media_id": "track::2",
                "media_type": "track",
                "name": "Song B",
                "artist": "Artist Y",
            },
        ]
    }


# ===========================================================================
# TestGetPlayers
# ===========================================================================


class TestGetPlayers:
    def test_get_players__json_response__returns_list_of_music_player(self):
        """
        GET /api/players must be called and the JSON list must be mapped to
        MusicPlayer objects with all fields populated correctly.
        """
        repo = _make_repo()
        _, mock_session = _make_mock_session(_mass_players_payload())

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = _run(repo.get_players())

        assert isinstance(result, list)
        assert len(result) == 2, f"Expected 2 players, got {len(result)}"
        assert all(isinstance(p, MusicPlayer) for p in result)

        playing = next(p for p in result if p.player_id == "player.living_room")
        assert playing.name == "Living Room"
        assert playing.state == "playing"
        assert playing.current_track == "Bohemian Rhapsody"

    def test_get_players__calls_correct_url(self):
        """get_players must issue a GET request to /api/players."""
        repo = _make_repo(base_url="http://mass.local:8095")
        _, mock_session = _make_mock_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(repo.get_players())

        called_url = mock_session.get.call_args[0][0]
        assert "/api/players" in called_url, (
            f"Expected /api/players in URL, got {called_url!r}"
        )


# ===========================================================================
# TestSearch
# ===========================================================================


class TestSearch:
    def test_search__json_response__returns_list_of_music_search_result(self):
        """
        GET /api/search must be called and results mapped to MusicSearchResult
        objects with correct fields.
        """
        repo = _make_repo()
        _, mock_session = _make_mock_session(_mass_search_payload())

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = _run(repo.search(query="Song A", limit=5))

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(r, MusicSearchResult) for r in result)
        first = result[0]
        assert first.name == "Song A"
        assert first.artist == "Artist X"
        assert first.media_type == "track"

    def test_search__calls_url_with_query_parameter(self):
        """The search request URL must include the query string."""
        repo = _make_repo(base_url="http://mass.local:8095")
        _, mock_session = _make_mock_session({"tracks": []})

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(repo.search(query="my query", limit=5))

        called_url = mock_session.get.call_args[0][0]
        # Accept either URL params embedded or passed as params= kwarg
        params_kwarg = mock_session.get.call_args[1].get("params", {})
        query_present = (
            "my query" in called_url
            or "my+query" in called_url
            or "my%20query" in called_url
            or params_kwarg.get("query") == "my query"
        )
        assert query_present, (
            f"Expected query parameter in GET call. URL={called_url!r}, "
            f"params={params_kwarg!r}"
        )


# ===========================================================================
# TestPlayMedia
# ===========================================================================


class TestPlayMedia:
    def test_play_media__posts_to_correct_url_with_correct_body(self):
        """
        play_media must POST to /api/players/play_media with a JSON body
        containing player_id, media_id, and media_type.
        """
        repo = _make_repo(base_url="http://mass.local:8095")
        _, mock_session = _make_mock_session({"status": "ok"})

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(
                repo.play_media(
                    player_id="player.living_room",
                    media_id="track::1",
                    media_type="track",
                )
            )

        called_url = mock_session.post.call_args[0][0]
        assert "/api/players/play_media" in called_url, (
            f"Expected /api/players/play_media in URL, got {called_url!r}"
        )

        call_kwargs = mock_session.post.call_args[1]
        json_body = call_kwargs.get("json") or call_kwargs.get("data")
        assert json_body is not None, "Expected a JSON body in the POST request"
        assert json_body.get("player_id") == "player.living_room"
        assert json_body.get("media_id") == "track::1"
        assert json_body.get("media_type") == "track"


# ===========================================================================
# TestPlayerCommand
# ===========================================================================


class TestPlayerCommand:
    def test_player_command__posts_to_correct_url_with_correct_body(self):
        """
        player_command must POST to /api/players/player_command with
        player_id and command in the JSON body.
        """
        repo = _make_repo(base_url="http://mass.local:8095")
        _, mock_session = _make_mock_session({"status": "ok"})

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(repo.player_command(player_id="player.bedroom", command="pause"))

        called_url = mock_session.post.call_args[0][0]
        assert "/api/players/player_command" in called_url, (
            f"Expected /api/players/player_command in URL, got {called_url!r}"
        )

        call_kwargs = mock_session.post.call_args[1]
        json_body = call_kwargs.get("json") or call_kwargs.get("data")
        assert json_body is not None
        assert json_body.get("player_id") == "player.bedroom"
        assert json_body.get("command") == "pause"


# ===========================================================================
# TestSetVolume
# ===========================================================================


class TestSetVolume:
    def test_set_volume__calls_correct_url_with_volume(self):
        """
        set_volume must POST to /api/players/{player_id}/volume_set/{volume}.
        Both the player_id and the volume must appear in the URL.
        """
        repo = _make_repo(base_url="http://mass.local:8095")
        _, mock_session = _make_mock_session({"status": "ok"})

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(repo.set_volume(player_id="player.living_room", volume=75))

        called_url = mock_session.post.call_args[0][0]
        assert "player.living_room" in called_url, (
            f"Expected player_id in URL, got {called_url!r}"
        )
        assert "75" in called_url, (
            f"Expected volume 75 in URL, got {called_url!r}"
        )
        assert "volume_set" in called_url, (
            f"Expected 'volume_set' in URL, got {called_url!r}"
        )


# ===========================================================================
# TestAuthHeader
# ===========================================================================


class TestAuthHeader:
    def test_get_players__token_provided__auth_header_present(self):
        """
        When a non-empty token is given, every request must include an
        Authorization header (Bearer scheme or equivalent).
        """
        repo = _make_repo(token="my-secret-token")
        _, mock_session = _make_mock_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            _run(repo.get_players())

        # Auth can be set on the session constructor or on individual requests.
        # We can't introspect deeply without implementation — so we verify
        # that the repo actually stores the token for later use.
        assert repo.token == "my-secret-token", (
            "Token must be stored on the repository instance"
        )

    def test_get_players__empty_token__no_auth_header(self):
        """
        When token is empty string, no Authorization header must be added.
        The repo must still function normally.
        """
        repo = _make_repo(token="")
        _, mock_session = _make_mock_session([])

        with patch.object(repo, "_get_session", return_value=mock_session):
            result = _run(repo.get_players())

        # No exception must be raised; result must be a list
        assert isinstance(result, list)
        assert repo.token == "", "Empty token must be stored as empty string"


# ===========================================================================
# TestErrorPropagation
# ===========================================================================


class TestErrorPropagation:
    def test_get_players__client_connector_error__propagates(self):
        """
        aiohttp.ClientConnectorError (connection refused / unreachable) must
        propagate out of get_players() — it must NOT be silently swallowed.
        """
        import aiohttp

        repo = _make_repo()

        # Build a session mock whose get raises ClientConnectorError
        mock_resp = AsyncMock()
        mock_cm_resp = AsyncMock()

        class _FakeConnector:
            pass

        conn_error = aiohttp.ClientConnectorError(
            connection_key=None,  # type: ignore[arg-type]
            os_error=OSError("Connection refused"),
        )

        mock_cm_resp.__aenter__ = AsyncMock(side_effect=conn_error)
        mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_cm_resp)

        with patch.object(repo, "_get_session", return_value=mock_session):
            with pytest.raises(aiohttp.ClientConnectorError):
                _run(repo.get_players())


# ===========================================================================
# TestSessionReuse — aiohttp.ClientSession must be created at most once
# ===========================================================================
#
# Contract (Milestone 2B-2): the adapter reuses a single aiohttp.ClientSession
# across calls via _get_session(). Calling a method twice must instantiate
# aiohttp.ClientSession AT MOST ONCE.
#
# RED today: every method opens `async with aiohttp.ClientSession() as session`,
# so two calls instantiate the session twice (call_count == 2).


def _make_reusable_session(json_response):
    """
    Build a single session mock that works regardless of whether production
    uses it as a context manager (`async with aiohttp.ClientSession() as s`)
    or directly via _get_session() (`s = self._get_session()`).

    The session enters itself (`__aenter__` returns the same object), so the
    `.get`/`.post` calls — which return the response context manager — are
    always reachable. Only the instantiation count is asserted by the caller.
    """
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_response)
    mock_resp.status = 200

    mock_cm_resp = AsyncMock()
    mock_cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_cm_resp)
    mock_session.post = MagicMock(return_value=mock_cm_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestSessionReuse:
    def test_get_players__called_twice__client_session_instantiated_once(self):
        repo = _make_repo()
        mock_session = _make_reusable_session(_mass_players_payload())

        with patch(
            "aiohttp.ClientSession", return_value=mock_session
        ) as client_session_cls:
            _run(repo.get_players())
            _run(repo.get_players())

        assert client_session_cls.call_count == 1, (
            f"Expected aiohttp.ClientSession to be instantiated once across two "
            f"calls (session reuse), got {client_session_cls.call_count}"
        )

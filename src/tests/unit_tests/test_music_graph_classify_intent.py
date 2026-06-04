"""
MusicGraph._classify_intent Unit Tests (TDD — RED phase)

Covers the classify node of MusicGraph.  The node must:
  - Parse the LLM JSON output and populate intent + state fields.
  - Resolve player_name → player_id by calling music_service.get_players().
  - When player_name is empty AND multiple players exist → add "select_player"
    to the intent list.
  - When player_name is empty AND exactly one player exists → auto-select that
    player (do NOT add "select_player").
  - Gracefully fall back to ["not_recognized"] on invalid JSON.

Pattern: identical to test_smart_home_lights_graph_classify_intent.py.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from application.graphs.music_graph import MusicGraph
    from domain.entities import MusicPlayer
except ImportError:
    pytest.skip(
        "MusicGraph not yet implemented — RED phase",
        allow_module_level=True,
    )


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_player(
    player_id: str = "player.living_room",
    name: str = "Living Room",
    state: str = "idle",
) -> MusicPlayer:
    return MusicPlayer(
        player_id=player_id,
        name=name,
        state=state,
        volume_level=0.5,
        current_track=None,
    )


def _make_graph(players: list = None) -> MusicGraph:
    """
    Build a MusicGraph with all external dependencies mocked so that the
    unit under test (_classify_intent) runs in full isolation.

    - llm_chat: mocked — its return value is controlled per test via
      _configure_cleaned_output().
    - music_service: mocked — get_players() returns the provided list.
    - load_prompt: patched to return a minimal "{input}" template.
    """
    llm_chat = MagicMock()
    music_service = MagicMock()
    music_service.get_players = AsyncMock(return_value=players or [])

    with patch.object(MusicGraph, "load_prompt", return_value="{input}"):
        graph = MusicGraph(
            llm_chat=llm_chat,
            music_service=music_service,
        )

    return graph


def _configure_cleaned_output(graph: MusicGraph, cleaned_str: str) -> None:
    """
    Bypass the LLM call entirely: patch _remove_thinking_tag so that
    _classify_intent receives cleaned_str as the already-cleaned LLM output.
    """
    graph._remove_thinking_tag = MagicMock(return_value=cleaned_str)


def _invoke(graph: MusicGraph, message: str = "toca uma música") -> dict:
    """Helper to call _classify_intent with a minimal state dict."""
    from domain.entities import GraphInvokeRequest, User

    user = User(id="u1", external_id="u1", name="Test")
    request = GraphInvokeRequest(message=message, user=user)
    return graph._classify_intent({"input": request})


# ===========================================================================
# TestClassifyIntentPlayMedia
# ===========================================================================


class TestClassifyIntentPlayMedia:
    def test_classify__play_media_intent__extracts_query_and_type(self):
        """
        When the LLM returns play_media intent, classify must populate
        play_media_query and play_media_type from the JSON payload.
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["play_media"], "play_media_query": "Bohemian Rhapsody", '
            '"play_media_type": "track", "player_name": ""}',
        )

        result = _invoke(graph)

        assert "play_media" in result["intent"], (
            f"Expected 'play_media' in intent, got {result['intent']!r}"
        )
        assert result.get("play_media_query") == "Bohemian Rhapsody", (
            f"Expected play_media_query='Bohemian Rhapsody', got {result!r}"
        )
        assert result.get("play_media_type") == "track", (
            f"Expected play_media_type='track', got {result!r}"
        )


# ===========================================================================
# TestClassifyIntentPlayerCommand
# ===========================================================================


class TestClassifyIntentPlayerCommand:
    def test_classify__player_command_next__extracts_command_value(self):
        """
        When the LLM returns player_command intent with command='next',
        classify must populate player_command_value='next'.
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["player_command"], "player_command_value": "next", '
            '"player_name": ""}',
        )

        result = _invoke(graph, message="próxima música")

        assert "player_command" in result["intent"]
        assert result.get("player_command_value") == "next", (
            f"Expected player_command_value='next', got {result!r}"
        )


# ===========================================================================
# TestClassifyIntentSetVolume
# ===========================================================================


class TestClassifyIntentSetVolume:
    def test_classify__set_volume_absolute__extracts_volume_value(self):
        """
        Absolute volume command: classify must populate set_volume_value='50'.
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["set_volume"], "set_volume_value": "50", '
            '"set_volume_direction": null, "player_name": ""}',
        )

        result = _invoke(graph, message="volume 50")

        assert "set_volume" in result["intent"]
        assert result.get("set_volume_value") == "50", (
            f"Expected set_volume_value='50', got {result!r}"
        )

    def test_classify__set_volume_relative_up__extracts_direction(self):
        """
        Relative volume command 'up': classify must populate
        set_volume_direction='up'.
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["set_volume"], "set_volume_value": null, '
            '"set_volume_direction": "up", "player_name": ""}',
        )

        result = _invoke(graph, message="aumenta o volume")

        assert "set_volume" in result["intent"]
        assert result.get("set_volume_direction") == "up", (
            f"Expected set_volume_direction='up', got {result!r}"
        )


# ===========================================================================
# TestClassifyIntentNowPlaying
# ===========================================================================


class TestClassifyIntentNowPlaying:
    def test_classify__now_playing_intent__sets_now_playing_value(self):
        """
        now_playing intent: classify must populate now_playing_value='true'.
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["now_playing"], "now_playing_value": "true", '
            '"player_name": ""}',
        )

        result = _invoke(graph, message="o que está tocando?")

        assert "now_playing" in result["intent"]
        assert result.get("now_playing_value") == "true", (
            f"Expected now_playing_value='true', got {result!r}"
        )


# ===========================================================================
# TestClassifyIntentPlayerSelection
# ===========================================================================


class TestClassifyIntentPlayerSelection:
    def test_classify__no_player_name_multiple_players__adds_select_player_intent(
        self,
    ):
        """
        When player_name is empty AND there are multiple players, classify
        must add 'select_player' to the intent list so the user is prompted
        to choose.
        """
        players = [
            _sample_player("player.living_room", "Living Room"),
            _sample_player("player.bedroom", "Bedroom"),
        ]
        graph = _make_graph(players=players)
        _configure_cleaned_output(
            graph,
            '{"intent": ["play_media"], "play_media_query": "Song A", '
            '"play_media_type": "track", "player_name": ""}',
        )

        result = _invoke(graph)

        assert "select_player" in result["intent"], (
            f"Expected 'select_player' when player_name empty + multiple players, "
            f"got {result['intent']!r}"
        )

    def test_classify__no_player_name_single_player__auto_selects_no_select_player(
        self,
    ):
        """
        When player_name is empty AND there is exactly one player, classify
        must auto-select it and NOT add 'select_player' to the intent.
        player_id must be set in the state.
        """
        players = [_sample_player("player.kitchen", "Kitchen")]
        graph = _make_graph(players=players)
        _configure_cleaned_output(
            graph,
            '{"intent": ["play_media"], "play_media_query": "Jazz", '
            '"play_media_type": "playlist", "player_name": ""}',
        )

        result = _invoke(graph)

        assert "select_player" not in result.get("intent", []), (
            f"'select_player' must NOT appear when there is only one player, "
            f"got {result['intent']!r}"
        )
        assert result.get("player_id") == "player.kitchen", (
            f"Expected player_id='player.kitchen' (auto-selected), got {result!r}"
        )


# ===========================================================================
# TestClassifyIntentNotRecognized
# ===========================================================================


class TestClassifyIntentNotRecognized:
    def test_classify__not_recognized_fallback__sets_not_recognized_intent(self):
        """
        When the LLM emits not_recognized, the intent must be ['not_recognized'].
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(
            graph,
            '{"intent": ["not_recognized"], "player_name": ""}',
        )

        result = _invoke(graph, message="blablabla")

        assert "not_recognized" in result["intent"], (
            f"Expected 'not_recognized' in intent, got {result['intent']!r}"
        )

    def test_classify__invalid_json__falls_back_to_not_recognized_without_crash(self):
        """
        When the LLM returns invalid JSON, classify must NOT raise an exception
        and must fall back to ['not_recognized'].
        """
        graph = _make_graph(players=[_sample_player()])
        _configure_cleaned_output(graph, "this is not json at all {{{{")

        result = _invoke(graph, message="some message")

        assert "not_recognized" in result.get("intent", []), (
            f"Expected 'not_recognized' fallback on invalid JSON, got {result!r}"
        )

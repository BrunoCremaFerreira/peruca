"""
MusicGraph multi-intent fan-out unit tests.

Regression coverage for the LangGraph ``InvalidUpdateError`` raised when the
classify node returns more than one intent that writes to the shared ``output``
channel (e.g. ``play_media`` + ``select_player``). LangGraph rejects two writes
to the same non-reduced key in a single super-step:

    InvalidUpdateError: At key 'output': Can receive only one value per step.

This surfaced once MainGraph started routing multi-intent messages
("acende as luzes e coloca uma playlist") to the music sub-graph. The graph must
fan out without crashing and still produce a single non-empty output string.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.graphs.music_graph import MusicGraph
from domain.entities import GraphInvokeRequest, MusicPlayer, User


def _player(player_id: str, name: str) -> MusicPlayer:
    return MusicPlayer(
        player_id=player_id,
        name=name,
        state="idle",
        volume_level=0.5,
        current_track=None,
    )


def _make_graph(players: list) -> MusicGraph:
    llm_chat = MagicMock()
    music_service = MagicMock()
    music_service.get_players = AsyncMock(return_value=players)
    music_service.search_and_play = AsyncMock(return_value="Tocando a playlist.")
    music_service.send_player_command = AsyncMock(return_value="Comando enviado.")
    music_service.set_volume = AsyncMock(return_value="Volume ajustado.")
    music_service.get_now_playing = AsyncMock(return_value="Tocando agora: X.")

    with patch.object(MusicGraph, "load_prompt", return_value="{input}"):
        return MusicGraph(llm_chat=llm_chat, music_service=music_service)


def _request(message: str) -> GraphInvokeRequest:
    return GraphInvokeRequest(
        message=message,
        user=User(id="u1", external_id="u1", name="Test"),
    )


class TestMusicGraphMultiIntentFanOut:
    def test_invoke__play_media_and_select_player__no_crash_nonempty_output(self):
        """
        Two players + empty player_name makes classify append 'select_player'
        alongside 'play_media'. Both nodes write 'output' in the same super-step;
        the graph must not raise and must return a non-empty output string.
        """
        graph = _make_graph(
            players=[_player("p1", "Sala"), _player("p2", "Quarto")]
        )
        graph._remove_thinking_tag = MagicMock(
            return_value=(
                '{"intent": ["play_media"], "play_media_query": "relaxante", '
                '"play_media_type": "playlist", "player_name": ""}'
            )
        )

        result = graph.invoke(invoke_request=_request("coloca uma playlist relaxante"))

        output = result.get("output")
        assert isinstance(output, str) and output.strip(), (
            f"Expected non-empty output, got {output!r}"
        )

    def test_invoke__single_intent__still_returns_output(self):
        """A plain single-intent play still works (no regression)."""
        graph = _make_graph(players=[_player("p1", "Sala")])
        graph._remove_thinking_tag = MagicMock(
            return_value=(
                '{"intent": ["play_media"], "play_media_query": "jazz", '
                '"play_media_type": "playlist", "player_name": ""}'
            )
        )

        result = graph.invoke(invoke_request=_request("toca jazz"))

        output = result.get("output")
        assert isinstance(output, str) and output.strip(), (
            f"Expected non-empty output, got {output!r}"
        )

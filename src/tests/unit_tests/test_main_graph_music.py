"""
MainGraph Music Integration Unit Tests (TDD — RED phase)

Covers the new 'music' intent routing introduced by the Music Assistant
feature.  MainGraph gains:
  - output_music: Optional[str] in MainGraphState
  - music_graph: MusicGraph = None in __init__()
  - _handle_music node that delegates to music_graph.invoke()
  - _classify_intent passes context_hints["music_is_playing"] to the LLM chain

All sub-graphs and LLM calls are mocked.
Pattern: identical to existing main_graph test files.
"""

from unittest.mock import MagicMock, patch
import uuid

import pytest

try:
    from application.graphs.main_graph import MainGraph
    from application.graphs.music_graph import MusicGraph
    from domain.entities import GraphInvokeRequest, User
except ImportError:
    pytest.skip(
        "MainGraph music extension or MusicGraph not yet implemented — RED phase",
        allow_module_level=True,
    )


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _sample_request(message: str = "toca jazz", context_hints: dict = None) -> GraphInvokeRequest:
    user = _sample_user()
    return GraphInvokeRequest(
        message=message,
        user=user,
        memories=[],
        context_hints=context_hints or {},
    )


def _make_main_graph(music_graph=None) -> MainGraph:
    """
    Build a MainGraph with all sub-graphs mocked.  load_prompt is patched to
    return a minimal "{input}" template so no filesystem access is needed.
    """
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = '["music"]'
    llm_chat.invoke.return_value = llm_response

    only_talk_graph = MagicMock()
    only_talk_graph.invoke.return_value = "ok"

    shopping_list_graph = MagicMock()
    shopping_list_graph.invoke.return_value = {"output": "lista ok"}

    smart_home_lights_graph = MagicMock()
    smart_home_lights_graph.invoke.return_value = {"output": "luz ok"}

    smart_home_climate_graph = MagicMock()
    smart_home_climate_graph.invoke.return_value = {"output": "clima ok"}

    smart_home_sensors_graph = MagicMock()
    smart_home_sensors_graph.invoke.return_value = {"output": "sensor ok"}

    with patch.object(MainGraph, "load_prompt", return_value="{input} {music_is_playing}"):
        graph = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=only_talk_graph,
            shopping_list_graph=shopping_list_graph,
            smart_home_lights_graph=smart_home_lights_graph,
            smart_home_climate_graph=smart_home_climate_graph,
            smart_home_sensors_graph=smart_home_sensors_graph,
            music_graph=music_graph,
        )

    return graph


# ===========================================================================
# TestMainGraphMusicRouting
# ===========================================================================


class TestMainGraphMusicRouting:
    def test_invoke__music_intent__handle_music_called_output_music_populated(self):
        """
        When the LLM classifies intent as ['music'], the graph must route to
        _handle_music and the final state must have output_music set.
        """
        music_graph = MagicMock(spec=MusicGraph)
        music_graph.invoke.return_value = {"output": "Tocando: Bohemian Rhapsody"}

        graph = _make_main_graph(music_graph=music_graph)
        # Override _remove_thinking_tag and LLM chain to emit "music" intent
        graph._remove_thinking_tag = MagicMock(return_value='["music"]')

        request = _sample_request(message="toca jazz")

        result = graph.invoke(invoke_request=request)

        music_graph.invoke.assert_called_once()
        assert result.get("output_music") is not None, (
            f"Expected output_music to be populated, got result={result!r}"
        )

    def test_invoke__music_graph_none__does_not_crash(self):
        """
        When music_graph is None (default), the graph must not raise.
        This preserves backward compatibility with existing deployments.
        The output for the music intent should be a graceful fallback string
        or the node should simply be absent from the graph.
        """
        graph = _make_main_graph(music_graph=None)
        graph._remove_thinking_tag = MagicMock(return_value='["only_talking"]')

        request = _sample_request(message="oi")

        # Must not raise regardless of music_graph being None
        result = graph.invoke(invoke_request=request)
        assert result is not None


# ===========================================================================
# TestMainGraphMusicContextHints
# ===========================================================================


class TestMainGraphMusicContextHints:
    def test_classify_intent__music_is_playing_true__passes_hint_to_llm_chain(self):
        """
        When GraphInvokeRequest.context_hints contains {"music_is_playing": True},
        _classify_intent must pass this information to the LLM chain so the
        model can use it for intent disambiguation.

        We verify by inspecting the chain.invoke() call_args for the presence
        of music_is_playing or equivalent key.
        """
        music_graph = MagicMock(spec=MusicGraph)
        music_graph.invoke.return_value = {"output": "ok"}

        graph = _make_main_graph(music_graph=music_graph)
        # Intercept the classify call at _remove_thinking_tag level
        graph._remove_thinking_tag = MagicMock(return_value='["only_talking"]')

        request = _sample_request(
            message="que música é essa?",
            context_hints={"music_is_playing": True},
        )

        graph.invoke(invoke_request=request)

        # Verify that the LLM was called (via .invoke() or directly as callable).
        # LangChain chains may call the model via .invoke() or as __call__ depending
        # on the version — accept either.
        invoke_calls = graph.llm_chat.invoke.call_args_list
        direct_calls = graph.llm_chat.call_args_list
        all_calls = invoke_calls + direct_calls
        assert len(all_calls) >= 1, (
            "LLM must have been invoked at least once (via .invoke or __call__)"
        )

        # Verify music_is_playing hint appears in the formatted payload.
        first_call = all_calls[0]
        payload = first_call[0][0] if first_call[0] else str(first_call[1])
        payload_str = str(payload)
        assert "Sim" in payload_str or "música tocando" in payload_str or "music_is_playing" in payload_str, (
            f"Expected music_is_playing hint in LLM chain payload, got: {payload_str!r}"
        )

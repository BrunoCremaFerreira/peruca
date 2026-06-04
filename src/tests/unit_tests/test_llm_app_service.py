"""
LlmAppService enrichment Unit Tests (TDD - RED phase)

LlmAppService gains a new dependency `user_memory_service` and, in chat(),
loads the user's memories synchronously and injects them into the
GraphInvokeRequest as `memories=[m.content for ...]` BEFORE invoking the
main graph. Extraction is NOT done here (moved to background MemoryAppService).

New constructor contract:
    LlmAppService(main_graph, context_repository, user_repository,
                  user_memory_service)

Behaviours covered:
  - memories loaded and passed to GraphInvokeRequest (captured via
    main_graph.invoke.call_args)
  - non-existent user still raises NofFoundValidationError (preserved)

Expected to FAIL with TypeError (extra ctor arg) / AttributeError until the
service is updated.

--- Music Assistant extension (TDD - RED phase) ---

LlmAppService gains a new optional dependency `music_service: MusicService`.
In chat(), it calls asyncio.run(music_service.get_players()) to determine
whether any player is currently in state "playing", then injects
context_hints={"music_is_playing": bool} into the GraphInvokeRequest.

New constructor contract (extended):
    LlmAppService(main_graph, context_repository, user_repository,
                  user_memory_service, music_service=None)

New behaviours covered:
  - get_players() called once per chat() invocation
  - music_is_playing=True when at least one player has state="playing"
  - music_is_playing=False when no player has state="playing"
  - Exception in get_players() → context_hints["music_is_playing"]=False (no propagation)
  - context_hints present in the GraphInvokeRequest passed to main_graph.invoke()
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User, UserMemory
from domain.exceptions import NofFoundValidationError

try:
    from domain.entities import MusicPlayer
    _MUSIC_PLAYER_AVAILABLE = True
except ImportError:
    _MUSIC_PLAYER_AVAILABLE = False


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_service(user=None, memories=None, music_service=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "ok", "intent": ["only_talking"]}

    context_repository = MagicMock()

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = memories or []

    kwargs = dict(
        main_graph=main_graph,
        context_repository=context_repository,
        user_repository=user_repository,
        user_memory_service=user_memory_service,
    )
    if music_service is not None:
        kwargs["music_service"] = music_service

    service = LlmAppService(**kwargs)
    return service, main_graph, user_memory_service


def _make_music_service(players=None):
    """Build a mock MusicService with get_players returning the given list."""
    music_service = MagicMock()
    music_service.get_players = AsyncMock(return_value=players or [])
    return music_service


# ===========================================================================
# TestLlmAppServiceEnrichment
# ===========================================================================


class TestLlmAppServiceEnrichment:
    def test_chat__loads_memories_and_passes_to_graph_request(self):
        # Arrange
        user = _sample_user()
        memories = [UserMemory(id=str(uuid.uuid4()), user_id=user.id, content="X")]
        service, main_graph, user_memory_service = _make_service(
            user=user, memories=memories
        )
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )
        # Act
        service.chat(request)
        # Assert
        user_memory_service.get_all_by_user.assert_called_once_with(user.id)
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.memories == ["X"]

    def test_chat__no_memories__passes_empty_list(self):
        # Arrange
        user = _sample_user()
        service, main_graph, _ = _make_service(user=user, memories=[])
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )
        # Act
        service.chat(request)
        # Assert
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.memories == []


# ===========================================================================
# TestLlmAppServiceErrors
# ===========================================================================


class TestLlmAppServiceErrors:
    def test_chat__unknown_user__raises_not_found(self):
        # Arrange
        service, main_graph, _ = _make_service(user=None)
        request = ChatRequest(
            message="oi", external_user_id=str(uuid.uuid4()), chat_id="c1"
        )
        # Act / Assert
        with pytest.raises(NofFoundValidationError):
            service.chat(request)
        main_graph.invoke.assert_not_called()


# ===========================================================================
# TestLlmAppServiceMusicContextHints  (Music Assistant extension — RED phase)
# ===========================================================================


@pytest.mark.skipif(
    not _MUSIC_PLAYER_AVAILABLE,
    reason="MusicPlayer entity not yet implemented — RED phase",
)
class TestLlmAppServiceMusicContextHints:
    def test_chat__calls_get_players_once_per_invocation(self):
        """
        chat() must call music_service.get_players() exactly once per
        request to determine the current playback state.
        """
        user = _sample_user()
        music_service = _make_music_service(players=[])
        service, main_graph, _ = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        service.chat(request)

        music_service.get_players.assert_called_once()

    def test_chat__player_playing__music_is_playing_true_in_context_hints(self):
        """
        When at least one player has state='playing', context_hints must
        contain {"music_is_playing": True}.
        """
        user = _sample_user()
        playing_player = MusicPlayer(
            player_id="player.living_room",
            name="Living Room",
            state="playing",
        )
        music_service = _make_music_service(players=[playing_player])
        service, main_graph, _ = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="que música é essa?",
            external_user_id=user.external_id,
            chat_id="c1",
        )

        service.chat(request)

        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert hasattr(graph_request, "context_hints"), (
            "GraphInvokeRequest must have context_hints attribute"
        )
        assert graph_request.context_hints.get("music_is_playing") is True, (
            f"Expected music_is_playing=True, got: {graph_request.context_hints!r}"
        )

    def test_chat__no_player_playing__music_is_playing_false_in_context_hints(self):
        """
        When no player has state='playing', context_hints must contain
        {"music_is_playing": False}.
        """
        user = _sample_user()
        idle_player = MusicPlayer(
            player_id="player.bedroom",
            name="Bedroom",
            state="idle",
        )
        music_service = _make_music_service(players=[idle_player])
        service, main_graph, _ = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        service.chat(request)

        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.context_hints.get("music_is_playing") is False, (
            f"Expected music_is_playing=False, got: {graph_request.context_hints!r}"
        )

    def test_chat__get_players_raises__music_is_playing_false_not_propagated(self):
        """
        When music_service.get_players() raises any exception, chat() must
        NOT propagate the exception. context_hints["music_is_playing"] must
        be False (graceful degradation).
        """
        user = _sample_user()
        music_service = MagicMock()
        music_service.get_players = AsyncMock(
            side_effect=RuntimeError("MASS unreachable")
        )
        service, main_graph, _ = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        # Must not raise
        service.chat(request)

        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.context_hints.get("music_is_playing") is False, (
            f"Expected music_is_playing=False on error, got: "
            f"{graph_request.context_hints!r}"
        )

    def test_chat__context_hints_present_in_graph_invoke_request(self):
        """
        The GraphInvokeRequest passed to main_graph.invoke() must have a
        context_hints dict (even when music_service is not provided / returns
        no players).
        """
        user = _sample_user()
        music_service = _make_music_service(players=[])
        service, main_graph, _ = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        service.chat(request)

        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert hasattr(graph_request, "context_hints"), (
            "GraphInvokeRequest must expose context_hints attribute"
        )
        assert isinstance(graph_request.context_hints, dict), (
            f"context_hints must be a dict, got {type(graph_request.context_hints)!r}"
        )

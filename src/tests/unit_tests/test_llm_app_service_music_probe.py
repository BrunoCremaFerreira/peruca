"""
LlmAppService music-probe timebox Unit Tests (TDD - RED phase).

--- Change #7: Timebox the music probe in LlmAppService.chat() ---

Today chat() runs, on EVERY message and BEFORE intent classification:

    players = async_runner.run(self.music_service.get_players())

with no time limit. If Music Assistant is slow/offline this blocks for
seconds with the GPU idle.

Desired contract:
  - A module-level constant ``_MUSIC_PROBE_TIMEOUT`` (e.g. 2.0 seconds).
  - The probe coroutine is wrapped with
    ``asyncio.wait_for(self.music_service.get_players(), timeout=_MUSIC_PROBE_TIMEOUT)``
    so the existing ``except Exception`` catches the resulting
    ``asyncio.TimeoutError`` and proceeds with ``music_is_playing=False``.
  - chat() must NEVER fail nor block (beyond the timeout) because of the probe.
  - With ``music_service=None`` the probe is skipped entirely (no exception).

These tests are expected to FAIL today:
  - The slow-probe test blocks for the full sleep (no wait_for), so the
    wall-clock assertion fails (RED for the right reason).
  - The constant-existence test fails because ``_MUSIC_PROBE_TIMEOUT`` does
    not exist yet (AttributeError).

They DO NOT touch production code.
"""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import application.appservices.llm_app_service as llm_module
from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_service(user=None, memories=None, music_service=None):
    """Build an LlmAppService with mocked collaborators.

    main_graph.invoke returns a deterministic dict so chat() can complete
    and return a normal result regardless of the music probe outcome.
    """
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "ok", "intent": ["only_talking"]}

    context_repository = MagicMock()

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = memories or []

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=context_repository,
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        music_service=music_service,
    )
    return service, main_graph


# ===========================================================================
# TestMusicProbeTimebox
# ===========================================================================


class TestMusicProbeTimebox:
    def test_chat__slow_probe__completes_without_blocking_beyond_timeout(self):
        """
        When music_service.get_players() is slow (e.g. MASS offline), chat()
        must still complete quickly: the probe is timeboxed by
        _MUSIC_PROBE_TIMEOUT and the slow coroutine is abandoned.

        RED today: there is no wait_for, so the probe blocks for the full
        sleep (well beyond the intended 2s timebox).
        """
        user = _sample_user()

        async def _slow_get_players():
            # Far longer than the intended ~2s probe timeout.
            await asyncio.sleep(12)
            return []

        music_service = MagicMock()
        music_service.get_players = AsyncMock(side_effect=_slow_get_players)

        service, main_graph = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        start = time.monotonic()
        result = service.chat(request)
        elapsed = time.monotonic() - start

        # Must complete well within a small budget above the ~2s timebox.
        assert elapsed < 5, (
            f"chat() blocked {elapsed:.1f}s on a slow music probe; expected it "
            f"to be timeboxed (~_MUSIC_PROBE_TIMEOUT) and return quickly"
        )
        # Chat still returns a normal main_graph result.
        assert result == {"intents": ["only_talking"], "output": "ok"}
        main_graph.invoke.assert_called_once()
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.context_hints.get("music_is_playing") is False

    def test_chat__probe_timeout_error__music_is_playing_false_and_no_raise(self):
        """
        When the probe raises asyncio.TimeoutError (as wait_for would on
        timeout), chat() must swallow it and proceed with
        music_is_playing=False, returning the normal main_graph result.
        """
        user = _sample_user()

        music_service = MagicMock()
        music_service.get_players = AsyncMock(side_effect=asyncio.TimeoutError())

        service, main_graph = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        # Must not raise.
        result = service.chat(request)

        assert result == {"intents": ["only_talking"], "output": "ok"}
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.context_hints.get("music_is_playing") is False, (
            f"Expected music_is_playing=False on probe timeout, got: "
            f"{graph_request.context_hints!r}"
        )

    def test_chat__probe_uses_wait_for_with_module_timeout_constant(self):
        """
        The probe must be timeboxed with asyncio.wait_for(..., timeout=
        _MUSIC_PROBE_TIMEOUT). We assert that wait_for is invoked with the
        module constant as timeout.

        RED today: the constant does not exist and wait_for is not used.
        """
        # Constant must exist on the module.
        assert hasattr(llm_module, "_MUSIC_PROBE_TIMEOUT"), (
            "llm_app_service must define a module-level _MUSIC_PROBE_TIMEOUT"
        )
        expected_timeout = llm_module._MUSIC_PROBE_TIMEOUT
        assert expected_timeout == 2.0, (
            f"_MUSIC_PROBE_TIMEOUT should be 2.0, got {expected_timeout!r}"
        )

        user = _sample_user()
        music_service = MagicMock()
        music_service.get_players = AsyncMock(return_value=[])
        service, main_graph = _make_service(user=user, music_service=music_service)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        real_wait_for = asyncio.wait_for

        with patch.object(
            llm_module.asyncio, "wait_for", wraps=real_wait_for
        ) as wait_for_spy:
            service.chat(request)

        assert wait_for_spy.called, (
            "music probe coroutine must be wrapped in asyncio.wait_for"
        )
        # timeout passed as kwarg or positional.
        call = wait_for_spy.call_args
        timeout_value = call.kwargs.get("timeout")
        if timeout_value is None and len(call.args) >= 2:
            timeout_value = call.args[1]
        assert timeout_value == expected_timeout, (
            f"wait_for must be called with timeout=_MUSIC_PROBE_TIMEOUT "
            f"({expected_timeout}), got {timeout_value!r}"
        )

    def test_chat__no_music_service__probe_skipped_no_exception(self):
        """
        With music_service=None the probe is skipped entirely: chat() must
        not raise and context_hints must not claim music is playing.
        """
        user = _sample_user()
        service, main_graph = _make_service(user=user, music_service=None)
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )

        result = service.chat(request)

        assert result == {"intents": ["only_talking"], "output": "ok"}
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        # No music_service → no music_is_playing hint set (stays absent/falsey).
        assert not graph_request.context_hints.get("music_is_playing")

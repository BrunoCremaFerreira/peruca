"""
HTTP adapter ClientSession timeout Unit Tests (TDD - RED phase).

--- Change #5: Timeout on the ClientSession of the 5 HTTP adapters ---

Today each adapter's _get_session() creates aiohttp.ClientSession(headers=...)
WITHOUT a timeout. aiohttp's default total timeout is 300s, so an unreachable
host can hang for seconds, leaving the GPU idle between LLM calls.

Desired contract: every _get_session() must create the session with
    timeout=aiohttp.ClientTimeout(connect=5, total=30)
(connect=5 fails fast on an unreachable host; total=30 is a generous ceiling).

These tests are expected to FAIL today because no timeout kwarg is passed.

They DO NOT touch production code. They patch aiohttp.ClientSession and only
inspect the kwargs used to construct it, so existing adapter behaviour tests
(which patch _get_session) and TestSessionReuse (which only check call_count)
are unaffected.

Adapters covered:
  - HomeAssistantSmartHomeLightRepository
  - HomeAssistantSmartHomeClimateRepository
  - HomeAssistantSmartHomeSensorRepository
  - HomeAssistantSmartHomeCameraRepository
  - MusicAssistantMusicRepository
"""

from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import (
    HomeAssistantSmartHomeLightRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_climate_repository import (
    HomeAssistantSmartHomeClimateRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_sensor_repository import (
    HomeAssistantSmartHomeSensorRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_camera_repository import (
    HomeAssistantSmartHomeCameraRepository,
)
from infra.data.external.music.music_assistant.music_assistant_music_repository import (
    MusicAssistantMusicRepository,
)


EXPECTED_CONNECT = 5
EXPECTED_TOTAL = 30


def _build_repo(repo_cls):
    """Every adapter constructor accepts (base_url, token)."""
    return repo_cls("http://localhost:8123", "token")


def _assert_timeout_kwarg(client_session_cls):
    """Assert ClientSession was constructed once with the expected timeout."""
    assert client_session_cls.called, "aiohttp.ClientSession was not instantiated"
    _, kwargs = client_session_cls.call_args
    assert "timeout" in kwargs, (
        "aiohttp.ClientSession must be created with a timeout= kwarg "
        f"(got kwargs={list(kwargs)})"
    )
    timeout = kwargs["timeout"]
    assert isinstance(timeout, aiohttp.ClientTimeout), (
        f"timeout must be an aiohttp.ClientTimeout, got {type(timeout)!r}"
    )
    assert timeout.connect == EXPECTED_CONNECT, (
        f"ClientTimeout.connect must be {EXPECTED_CONNECT}, got {timeout.connect!r}"
    )
    assert timeout.total == EXPECTED_TOTAL, (
        f"ClientTimeout.total must be {EXPECTED_TOTAL}, got {timeout.total!r}"
    )


@pytest.mark.parametrize(
    "repo_cls",
    [
        HomeAssistantSmartHomeLightRepository,
        HomeAssistantSmartHomeClimateRepository,
        HomeAssistantSmartHomeSensorRepository,
        HomeAssistantSmartHomeCameraRepository,
        MusicAssistantMusicRepository,
    ],
    ids=["light", "climate", "sensor", "camera", "music"],
)
class TestAdapterSessionTimeout:
    def test_get_session__creates_clientsession_with_connect_and_total_timeout(
        self, repo_cls
    ):
        repo = _build_repo(repo_cls)

        with patch("aiohttp.ClientSession", return_value=MagicMock()) as cs:
            repo._get_session()

        _assert_timeout_kwarg(cs)

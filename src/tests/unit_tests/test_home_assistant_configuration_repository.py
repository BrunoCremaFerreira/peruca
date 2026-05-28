import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from websockets.exceptions import ConnectionClosed
from websockets.frames import Close

from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
    HomeAssistantSmartHomeConfigurationRepository,
)


"""
HomeAssistantSmartHomeConfigurationRepository Unit Tests

Covers Bug #6:
  The repository only checks `if self._ws is None` before connecting, so when
  the server closes an already-established connection `self._ws` still holds the
  stale (closed) object. The next send/recv raises ConnectionClosed which is
  currently unhandled and propagates to the caller.

  Expected behaviour after the fix: if ConnectionClosed is raised during send()
  or recv(), the client must close the stale connection, reconnect, and retry
  the operation once before propagating the error.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_connection_closed() -> ConnectionClosed:
    """Return a ConnectionClosed exception that simulates a server-side close."""
    return ConnectionClosed(Close(1001, "server going away"), None)


def _make_auth_sequence_responses() -> list:
    """
    Minimal sequence of JSON messages that _authenticate() expects:
      1. {"type": "auth_required"}
      2. {"type": "auth_ok"}
    """
    return [
        json.dumps({"type": "auth_required"}),
        json.dumps({"type": "auth_ok"}),
    ]


def _make_mock_ws(recv_responses: list) -> AsyncMock:
    """
    Build an AsyncMock WebSocket that returns messages from recv_responses
    in order, then raises StopAsyncIteration if exhausted.
    """
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=recv_responses)
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _make_repo() -> HomeAssistantSmartHomeConfigurationRepository:
    return HomeAssistantSmartHomeConfigurationRepository(
        websocket_url="ws://localhost:8123",
        token="test-token",
    )


# ---------------------------------------------------------------------------
# Bug #6 — get_all_exposed_entities_ids: ConnectionClosed → reconnect + retry
# ---------------------------------------------------------------------------


class TestGetAllExposedEntitiesIdsReconnectOnConnectionClosed:
    def test_get_all_exposed_entities_ids__connection_closed__reconnects_and_retries(
        self,
    ):
        """
        Bug: self._ws is not None after the first connect, but the server later
        closes the socket. The next recv() inside _send() raises ConnectionClosed.
        The repository must catch it, call _connect() again, and retry, returning
        the result from the second attempt instead of propagating the exception.
        """
        entity_list_response = json.dumps(
            {
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "entity_id": "light.sala",
                        "options": {"conversation": {"should_expose": True}},
                    },
                ],
            }
        )

        # First WebSocket: auth succeeds, then recv() in _send() raises ConnectionClosed
        first_ws = _make_mock_ws(
            recv_responses=(
                _make_auth_sequence_responses()  # two auth messages
                + [_make_connection_closed()]  # connection drops on first data recv
            )
        )

        # Second WebSocket (after reconnect): auth succeeds, then the real response
        second_ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [entity_list_response])
        )

        repo = _make_repo()
        connect_call_count = 0

        async def _fake_connect(url, **kwargs):
            nonlocal connect_call_count
            connect_call_count += 1
            if connect_call_count == 1:
                return first_ws
            return second_ws

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            side_effect=_fake_connect,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_all_exposed_entities_ids()
            )

        assert result == ["light.sala"], (
            f"Expected ['light.sala'] after reconnect, got {result!r}"
        )
        assert connect_call_count == 2, (
            f"Expected 2 connect() calls (initial + reconnect), got {connect_call_count}"
        )


# ---------------------------------------------------------------------------
# Bug #6 — get_aliases_by_entity_id: ConnectionClosed → reconnect + retry
# ---------------------------------------------------------------------------


class TestGetAliasesByEntityIdReconnectOnConnectionClosed:
    def test_get_aliases_by_entity_id__connection_closed__reconnects_and_retries(self):
        """
        Bug: same as above but for get_aliases_by_entity_id. A ConnectionClosed
        raised while waiting for the alias response must trigger a reconnect and
        a single retry that returns the correct alias list.
        """
        aliases_response = json.dumps(
            {
                "id": 1,
                "type": "result",
                "success": True,
                "result": {
                    "entity_id": "light.quarto",
                    "aliases": ["Quarto Principal", "Quarto"],
                },
            }
        )

        first_ws = _make_mock_ws(
            recv_responses=(
                _make_auth_sequence_responses() + [_make_connection_closed()]
            )
        )

        second_ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [aliases_response])
        )

        repo = _make_repo()
        connect_call_count = 0

        async def _fake_connect(url, **kwargs):
            nonlocal connect_call_count
            connect_call_count += 1
            if connect_call_count == 1:
                return first_ws
            return second_ws

        with patch(
            "infra.data.external.smart_home.home_assistant"
            ".home_assistant_smart_home_configuration_repository.websockets_connect",
            side_effect=_fake_connect,
        ):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_aliases_by_entity_id(entity_id="light.quarto")
            )

        assert result == ["Quarto Principal", "Quarto"], (
            f"Expected alias list after reconnect, got {result!r}"
        )
        assert connect_call_count == 2, (
            f"Expected 2 connect() calls (initial + reconnect), got {connect_call_count}"
        )

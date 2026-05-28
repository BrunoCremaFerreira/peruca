import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from websockets.exceptions import ConnectionClosed
from websockets.frames import Close

from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
    HomeAssistantSmartHomeConfigurationRepository,
)

try:
    from domain.entities import SmartHomeArea

    _AREA_AVAILABLE = True
except ImportError:
    SmartHomeArea = None  # type: ignore[assignment,misc]
    _AREA_AVAILABLE = False

_SKIP_IF_AREA_NOT_IMPLEMENTED = pytest.mark.skipif(
    not _AREA_AVAILABLE,
    reason="SmartHomeArea entity not implemented yet (TDD/RED phase)",
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


# ---------------------------------------------------------------------------
# Helpers for the area / exposed-entities tests (TDD — area feature)
# ---------------------------------------------------------------------------


def _make_ws_area_registry_payload(areas: list) -> str:
    """
    Simulate a Home Assistant WebSocket `config/area_registry/list` response.

    Each area dict should contain at least 'area_id' and 'name'.
    """
    return json.dumps(
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": areas,
        }
    )


def _make_ws_entity_registry_payload(entities: list) -> str:
    """
    Simulate a Home Assistant WebSocket `config/entity_registry/list` response.

    Each entity dict typically contains 'entity_id', 'area_id' and the
    'options.conversation.should_expose' flag used by the existing
    get_all_exposed_entities_ids() method.
    """
    return json.dumps(
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": entities,
        }
    )


def _patch_websockets_connect_returning(ws_sequence: list):
    """
    Helper that patches websockets_connect in the configuration repo module
    and returns each AsyncMock WebSocket from ws_sequence in order.
    """

    async def _fake_connect(url, **kwargs):
        return ws_sequence.pop(0)

    return patch(
        "infra.data.external.smart_home.home_assistant"
        ".home_assistant_smart_home_configuration_repository.websockets_connect",
        side_effect=_fake_connect,
    )


# ---------------------------------------------------------------------------
# TestGetAllAreas — TDD: get_all_areas() must return List[SmartHomeArea]
# ---------------------------------------------------------------------------


@_SKIP_IF_AREA_NOT_IMPLEMENTED
class TestGetAllAreas:
    def test_get_all_areas__ws_returns_areas__maps_to_entities(self):
        """
        Given a WS area_registry/list response with two areas, get_all_areas()
        must return two SmartHomeArea objects with area_id and name populated.
        """
        areas_payload = _make_ws_area_registry_payload(
            [
                {"area_id": "kitchen", "name": "Cozinha"},
                {"area_id": "living_room", "name": "Sala"},
            ]
        )

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [areas_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(repo.get_all_areas())

        assert isinstance(result, list)
        assert len(result) == 2, f"Expected 2 areas, got {len(result)}"
        assert all(isinstance(a, SmartHomeArea) for a in result), (
            f"Expected List[SmartHomeArea], got {[type(a) for a in result]!r}"
        )
        area_ids = {a.area_id for a in result}
        names = {a.name for a in result}
        assert area_ids == {"kitchen", "living_room"}
        assert names == {"Cozinha", "Sala"}

    def test_get_all_areas__empty_response__returns_empty_list(self):
        """An empty area_registry response must produce an empty list, not raise."""
        empty_payload = _make_ws_area_registry_payload([])

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [empty_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(repo.get_all_areas())

        assert result == [], f"Expected [] for empty registry, got {result!r}"

    def test_get_all_areas__ws_response_missing_result_key__raises(self):
        """
        When the WS response has no 'result' key (HA returned an error),
        get_all_areas() must raise — consistent with get_all_exposed_entities_ids.
        """
        bad_payload = json.dumps(
            {"id": 1, "type": "result", "success": False, "error": "boom"}
        )

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [bad_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            with pytest.raises(Exception):
                asyncio.get_event_loop().run_until_complete(repo.get_all_areas())


# ---------------------------------------------------------------------------
# TestGetExposedEntities — TDD: returns objects with entity_id + area_id
# ---------------------------------------------------------------------------


class TestGetExposedEntities:
    """
    get_exposed_entities() must return only entities flagged with
    options.conversation.should_expose == True, AND must surface the area_id
    of each entity (the existing get_all_exposed_entities_ids() drops it).
    The returned objects can be dicts or lightweight dataclasses; tests only
    require the two attributes/keys 'entity_id' and 'area_id' to be readable.
    """

    @staticmethod
    def _extract(item, key):
        """Read 'entity_id' / 'area_id' from either dict or object."""
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def test_get_exposed_entities__only_exposed_entities_returned(self):
        """Entities without should_expose=True must be filtered out."""
        entities_payload = _make_ws_entity_registry_payload(
            [
                {
                    "entity_id": "light.sala",
                    "area_id": "living_room",
                    "options": {"conversation": {"should_expose": True}},
                },
                {
                    "entity_id": "light.hidden",
                    "area_id": "garage",
                    "options": {"conversation": {"should_expose": False}},
                },
                {
                    "entity_id": "light.no_options",
                    "area_id": "kitchen",
                    # no options at all
                },
            ]
        )

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [entities_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_exposed_entities()
            )

        ids = [self._extract(e, "entity_id") for e in result]
        assert ids == ["light.sala"], (
            f"Expected only ['light.sala'], got {ids!r}"
        )

    def test_get_exposed_entities__includes_area_id(self):
        """
        Unlike get_all_exposed_entities_ids() (which discards area_id), this
        new method MUST expose the area_id field for each entity.
        """
        entities_payload = _make_ws_entity_registry_payload(
            [
                {
                    "entity_id": "light.cozinha_1",
                    "area_id": "kitchen",
                    "options": {"conversation": {"should_expose": True}},
                },
            ]
        )

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [entities_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_exposed_entities()
            )

        assert len(result) == 1
        assert self._extract(result[0], "entity_id") == "light.cozinha_1"
        assert self._extract(result[0], "area_id") == "kitchen", (
            "get_exposed_entities() must surface the area_id of each entity"
        )

    def test_get_exposed_entities__entity_without_area_id__area_id_is_none(self):
        """
        An exposed entity without area_id (HA reports null) must still appear
        with area_id == None (not be silently dropped).
        """
        entities_payload = _make_ws_entity_registry_payload(
            [
                {
                    "entity_id": "light.orphan",
                    "area_id": None,
                    "options": {"conversation": {"should_expose": True}},
                },
            ]
        )

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [entities_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_exposed_entities()
            )

        assert len(result) == 1
        assert self._extract(result[0], "entity_id") == "light.orphan"
        assert self._extract(result[0], "area_id") is None

    def test_get_exposed_entities__empty_registry__returns_empty_list(self):
        empty_payload = _make_ws_entity_registry_payload([])

        ws = _make_mock_ws(
            recv_responses=(_make_auth_sequence_responses() + [empty_payload])
        )

        repo = _make_repo()

        with _patch_websockets_connect_returning([ws]):
            result = asyncio.get_event_loop().run_until_complete(
                repo.get_exposed_entities()
            )

        assert result == []

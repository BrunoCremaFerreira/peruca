"""
MainGraph must forward the request INTACT to every sub-graph — TZ-009 (latent).

`_handle_smart_home_security_cams` (main_graph.py) is the only handler that does not
pass `data["input"]` through: it REBUILDS the request

    GraphInvokeRequest(message=data["input"].message, user=data["input"].user)

dropping `memories`, `context_hints`, `images` — and now `user_timezone`, which
silently becomes "". Today the cameras graph never formats a date, so nothing breaks;
the day it does (a snapshot timestamp, "houve movimento às 22h"), it will raise
`ValidationError` from `clock` on a code path nobody touched. Latent by definition.

Contract fixed by these tests: the cameras handler forwards the ORIGINAL request, the
same way every other handler does — `invoke(invoke_request=data["input"])`.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

try:
    from application.graphs.main_graph import MainGraph
    from domain.entities import GraphInvokeRequest, User
except ImportError:  # pragma: no cover
    pytest.skip("MainGraph not importable", allow_module_level=True)


_TZ = "Asia/Tokyo"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _make(intent):
    llm_chat = MagicMock()
    response = MagicMock()
    response.content = f'["{intent}"]'
    llm_chat.invoke.return_value = response
    llm_chat.return_value = response

    def _mk(name):
        graph = MagicMock()
        graph.invoke.return_value = {"output": f"{name} ok"}
        return graph

    cameras = _mk("cams")
    sensors = _mk("sensors")

    with patch.object(MainGraph, "load_prompt", return_value="{input}"):
        graph = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=_mk("talk"),
            shopping_list_graph=_mk("shop"),
            smart_home_lights_graph=_mk("lights"),
            smart_home_climate_graph=_mk("climate"),
            smart_home_sensors_graph=sensors,
            smart_home_cameras_graph=cameras,
        )
    return graph, cameras, sensors


def _req(message="tem alguém na porta?"):
    return GraphInvokeRequest(
        message=message,
        user=_user(),
        memories=["gosta de café"],
        context_hints={"music_is_playing": True},
        user_timezone=_TZ,
    )


def _forwarded(sub_graph):
    args, kwargs = sub_graph.invoke.call_args
    return kwargs.get("invoke_request") or (args[0] if args else None)


class TestCamerasRequestPreservesTheUserTimezone:
    def test_cameras__receives_the_user_timezone(self):
        graph, cameras, _ = _make("smart_home_security_cams")
        graph.invoke(invoke_request=_req())
        forwarded = _forwarded(cameras)
        assert forwarded is not None
        assert forwarded.user_timezone == _TZ

    def test_cameras__request_is_not_rebuilt_from_scratch(self):
        # Everything else the request carries must survive too — the rebuild drops
        # memories/context_hints/images as well.
        graph, cameras, _ = _make("smart_home_security_cams")
        request = _req()
        graph.invoke(invoke_request=request)
        forwarded = _forwarded(cameras)
        assert forwarded.memories == request.memories
        assert forwarded.context_hints == request.context_hints

    def test_sensors__already_forwards_the_timezone(self):
        # Regression anchor: the handler that gets it right must keep getting it right.
        graph, _, sensors = _make("smart_home_sensors")
        graph.invoke(invoke_request=_req(message="qual a temperatura?"))
        assert _forwarded(sensors).user_timezone == _TZ

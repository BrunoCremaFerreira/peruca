"""
MainGraph receipt routing unit tests (TDD - RED phase, plan §4.1 suite 5).
The classifier LLM and every sub-graph are mocked.

Contract under test (plan §3.1, stage 1):

- the classify payload gains a ``has_images`` context variable (same pattern
  as ``music_is_playing``), filled from ``request.images`` — the classifier
  itself NEVER sees the base64 payload;
- maintenance text + attached image routes to ``vehicle_maintenance`` and the
  images travel intact inside the routed GraphInvokeRequest (the sub-graph's
  vision node needs them);
- an image with text that does NOT ask to register anything ("olha essa
  foto") stays ``only_talking`` and the maintenance graph is never invoked
  (anti-generalization at the routing layer; the vision gate is the second
  line of defense);
- the empty-text + image bypass (straight to only_talking, zero LLM calls)
  stays intact — regression pin, this one is expected to stay green.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langgraph")

from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User


VALID_PNG = "data:image/png;base64,aGVsbG8="

# The real main_graph.md will reference {has_images} (plan §3.1): a classify
# payload without the key cannot even render the prompt.
_PROMPT_TEMPLATE = "{input} {has_images}"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno")


def _req(message, images=None):
    return GraphInvokeRequest(
        message=message,
        user=_user(),
        context_hints={},
        images=images or [],
    )


def _make(intent_content='["vehicle_maintenance"]'):
    llm_chat = MagicMock()
    resp = MagicMock()
    resp.content = intent_content
    # Cover both ways LangChain may coerce a mock in `prompt | llm_chat`.
    llm_chat.invoke.return_value = resp
    llm_chat.return_value = resp

    only_talk = MagicMock()
    only_talk.invoke.return_value = {"output": "conversa livre"}

    vehicle_graph = MagicMock()
    vehicle_graph.invoke.return_value = {
        "intent": ["register_from_receipt"],
        "output": "Encontrei estes dados no documento...",
    }

    def _mk(name):
        m = MagicMock()
        m.invoke.return_value = {"output": f"{name} ok"}
        return m

    with patch.object(MainGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        graph = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=only_talk,
            shopping_list_graph=_mk("shop"),
            smart_home_lights_graph=_mk("lights"),
            smart_home_climate_graph=_mk("climate"),
            smart_home_sensors_graph=_mk("sensors"),
            smart_home_cameras_graph=_mk("cams"),
            music_graph=None,
            vehicle_maintenance_graph=vehicle_graph,
        )
    return graph, llm_chat, only_talk, vehicle_graph


class TestReceiptIntentRouting:
    def test_maintenance_text_with_image__routes_to_vehicle_graph_with_images(self):
        graph, _, only_talk, vehicle_graph = _make(
            intent_content='["vehicle_maintenance"]'
        )
        request = _req("registra essa manutenção", images=[VALID_PNG])

        result = graph.invoke(invoke_request=request)

        vehicle_graph.invoke.assert_called_once()
        routed = vehicle_graph.invoke.call_args.kwargs["invoke_request"]
        assert routed.images == [VALID_PNG]
        assert "Encontrei" in result["output"]
        only_talk.invoke.assert_not_called()

    def test_classify_payload__carries_has_images_hint_and_no_base64(self):
        graph, _, _, _ = _make()

        captured = {}
        resp = MagicMock()
        resp.content = '["vehicle_maintenance"]'
        chain_mock = MagicMock()
        chain_mock.invoke.side_effect = (
            lambda payload, *a, **k: (captured.__setitem__("payload", payload) or resp)
        )
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = chain_mock
        graph.classification_prompt = prompt_mock

        graph._classify_intent(
            {"input": _req("registra essa nota", images=[VALID_PNG])}
        )

        payload = captured["payload"]
        assert "has_images" in payload
        assert "images" not in payload
        assert not any("data:image" in str(v) for v in payload.values())
        assert isinstance(payload["input"], str)


class TestPhotoCommentStaysConversation:
    def test_image_with_descriptive_text__routes_to_only_talking(self):
        # Anti-generalization: a photo plus "olha essa foto" is conversation,
        # never a maintenance action (the prompt rule decides; this pins the
        # plumbing when the classifier answers only_talking).
        graph, _, only_talk, vehicle_graph = _make(
            intent_content='["only_talking"]'
        )
        request = _req("olha essa foto", images=[VALID_PNG])

        result = graph.invoke(invoke_request=request)

        vehicle_graph.invoke.assert_not_called()
        only_talk.invoke.assert_called_once()
        routed = only_talk.invoke.call_args.kwargs["invoke_request"]
        assert routed.images == [VALID_PNG]
        assert "conversa livre" in result["output"]


class TestEmptyTextBypassRegression:
    def test_empty_text_with_image__bypasses_to_only_talking_without_llm(self):
        # Security control (main_graph.py:88-91): a photo alone never triggers
        # an action and never costs a classify call. Must stay intact.
        graph, llm_chat, _, _ = _make()

        result = graph._classify_intent({"input": _req("", images=[VALID_PNG])})

        assert result["intent"] == ["only_talking"]
        llm_chat.assert_not_called()
        llm_chat.invoke.assert_not_called()

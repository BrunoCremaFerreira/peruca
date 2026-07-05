"""
MainGraph image handling unit tests (TDD - RED phase).

Fase A constraints for the classifier and routing:
  - the classifier payload NEVER contains the images (cost/latency + parsing
    robustness); `input` stays a plain text string;
  - empty text + images present short-circuits to ["only_talking"] WITHOUT
    calling the classifier LLM;
  - images travel intact to the routed action node;
  - the only_talk `image_description` transits a side channel in the state and
    is NOT read by _handle_final_response (never leaks into `output`); it is
    None for non-vision intents.

Expected to FAIL until MainGraph is updated.
"""

import uuid
from unittest.mock import MagicMock, patch

from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User


VALID_PNG = "data:image/png;base64,aGVsbG8="


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _request(message="oi", images=None) -> GraphInvokeRequest:
    return GraphInvokeRequest(
        message=message,
        user=_sample_user(),
        memories=[],
        context_hints={},
        images=images or [],
    )


def _make_main_graph(intent_content='["only_talking"]', only_talk_result=None):
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = intent_content
    # The LCEL chain (prompt | llm_chat) invokes the coerced llm_chat as a
    # callable, so the CALL return value (not .invoke) is what flows downstream.
    llm_chat.return_value = llm_response
    llm_chat.invoke.return_value = llm_response

    only_talk = MagicMock()
    only_talk.invoke.return_value = (
        only_talk_result
        if only_talk_result is not None
        else {"output": "conversa", "image_description": None}
    )

    shopping = MagicMock()
    shopping.invoke.return_value = {"output": "lista ok"}

    other = MagicMock()
    other.invoke.return_value = {"output": "ok"}

    with patch.object(MainGraph, "load_prompt", return_value="{input} {music_is_playing}"):
        graph = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=only_talk,
            shopping_list_graph=shopping,
            smart_home_lights_graph=other,
            smart_home_climate_graph=other,
            smart_home_sensors_graph=other,
        )
    return graph, llm_chat, only_talk, shopping


class TestClassifyIntentIgnoresImages:
    def test_classifier_payload_has_no_image_key(self):
        graph, _, _, _ = _make_main_graph()

        captured = {}
        resp = MagicMock()
        resp.content = '["only_talking"]'
        chain_mock = MagicMock()
        chain_mock.invoke.side_effect = (
            lambda payload, *a, **k: (captured.__setitem__("payload", payload) or resp)
        )
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = chain_mock
        graph.classification_prompt = prompt_mock

        graph._classify_intent({"input": _request("o que é isso?", images=[VALID_PNG])})

        payload = captured["payload"]
        assert "images" not in payload
        assert not any("data:image" in str(v) for v in payload.values())
        assert isinstance(payload["input"], str)

    def test_images_reach_the_routed_action_node(self):
        graph, _, _, shopping = _make_main_graph(intent_content='["shopping_list"]')
        request = _request("adiciona leite na lista", images=[VALID_PNG])

        graph.invoke(request)

        routed_request = shopping.invoke.call_args[1]["invoke_request"]
        assert routed_request.images == [VALID_PNG]


class TestMainGraphImageShortCircuit:
    def test_empty_text_with_image__short_circuits_to_only_talking(self):
        graph, llm_chat, _, _ = _make_main_graph()

        result = graph._classify_intent({"input": _request("", images=[VALID_PNG])})

        assert result["intent"] == ["only_talking"]
        llm_chat.assert_not_called()

    def test_whitespace_text_with_image__short_circuits(self):
        graph, llm_chat, _, _ = _make_main_graph()

        result = graph._classify_intent({"input": _request("   ", images=[VALID_PNG])})

        assert result["intent"] == ["only_talking"]
        llm_chat.assert_not_called()

    def test_text_with_image__still_classifies_normally(self):
        graph, llm_chat, _, _ = _make_main_graph(intent_content='["shopping_list"]')

        result = graph._classify_intent(
            {"input": _request("adiciona leite", images=[VALID_PNG])}
        )

        assert result["intent"] == ["shopping_list"]
        llm_chat.assert_called()


class TestMainGraphImageDescriptionSideChannel:
    def test_image_description_transits_state_and_not_leaked_in_output(self):
        graph, _, _, _ = _make_main_graph(
            only_talk_result={"output": "Que fofo!", "image_description": "Um gato preto."}
        )
        request = _request("o que é isso?", images=[VALID_PNG])

        result = graph.invoke(request)

        assert result.get("image_description") == "Um gato preto."
        assert "Um gato preto." not in result["output"]

    def test_image_description_none_for_non_vision_intent(self):
        graph, _, _, _ = _make_main_graph(intent_content='["shopping_list"]')
        request = _request("adiciona leite", images=[])

        result = graph.invoke(request)

        assert result.get("image_description") is None

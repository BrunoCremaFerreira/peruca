"""
OnlyTalkGraph multimodal input + description unit tests (TDD - RED phase).

Fase A: OnlyTalkGraph builds a multimodal HumanMessage (text + image content
blocks) when images are present, keeps a plain-string content when not (zero
regression), reads (never writes) history, returns a dict
{"output", "image_description"}, and splits the response on the
<<<DESC_IMAGEM>>> marker. The marker directive is injected into the system
prompt ONLY when there is an image.

Assertions target the INTENTION (a text block + image block(s) exist), not a
fragile literal key.

Expected to FAIL until OnlyTalkGraph is updated.
"""

import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


_TZ = "America/Sao_Paulo"


_PROMPT_TEMPLATE = "{user_name}|{user_summary}|{user_memories}|{current_datetime}"
VALID_PNG = "data:image/png;base64,aGVsbG8="
VALID_JPEG = "data:image/jpeg;base64,/9j/AAAA"


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_history(messages=None):
    history = MagicMock()
    history.messages = messages or []
    return history


def _make_graph(get_session_history):
    llm_chat = MagicMock()
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        graph = OnlyTalkGraph(
            llm_chat=llm_chat,
            get_session_history=get_session_history,
        )
    return graph


def _invoke_capturing(graph, request, response_content="resposta"):
    """Short-circuit the LCEL chain, capturing chain input + system message."""
    captured = {}

    response = MagicMock()
    response.content = response_content

    chain_mock = MagicMock()

    def fake_invoke(payload, *args, **kwargs):
        captured["input"] = payload
        return response

    chain_mock.invoke.side_effect = fake_invoke

    def fake_from_messages(messages):
        captured["system"] = messages[0][1]
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = chain_mock
        return prompt_mock

    with patch(
        "application.graphs.only_talk_graph.ChatPromptTemplate.from_messages",
        side_effect=fake_from_messages,
    ):
        captured["result"] = graph.invoke(request)

    return captured


def _content_blocks(captured):
    """The content of the single HumanMessage passed under `input`."""
    input_messages = captured["input"]["input"]
    assert isinstance(input_messages, list) and len(input_messages) == 1
    return input_messages[0].content


class TestOnlyTalkGraphMultimodalInput:
    def test_no_image__content_is_plain_string(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(message="tudo bem?", user=_sample_user(), user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        content = _content_blocks(captured)
        assert content == "tudo bem?"
        assert captured["result"]["image_description"] is None

    def test_with_image__content_is_list_of_blocks(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="o que é isso?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        content = _content_blocks(captured)
        assert isinstance(content, list)
        # a text block AND an image block exist, and the data URI is carried.
        assert any(b.get("type") == "text" for b in content)
        image_blocks = [b for b in content if b.get("type") == "image_url"]
        assert len(image_blocks) == 1
        assert VALID_PNG in str(image_blocks[0])

    def test_multiple_images__n_image_blocks(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="olha essas", user=_sample_user(), images=[VALID_PNG, VALID_JPEG], user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        content = _content_blocks(captured)
        image_blocks = [b for b in content if b.get("type") == "image_url"]
        assert len(image_blocks) == 2

    def test_history_still_read_and_injected(self):
        prior = [HumanMessage(content="oi"), AIMessage(content="olá")]
        history = _make_history(prior)
        get_session_history = MagicMock(return_value=history)
        graph = _make_graph(get_session_history)
        request = GraphInvokeRequest(
            message="e agora?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        get_session_history.assert_called_once()
        assert captured["input"]["history"] == prior

    def test_never_writes_history(self):
        history = _make_history([HumanMessage(content="oi")])
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="e agora?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        _invoke_capturing(graph, request)

        history.add_messages.assert_not_called()


class TestOnlyTalkGraphImageDescription:
    def test_returns_dict_with_output_and_description(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="o que é isso?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        captured = _invoke_capturing(
            graph,
            request,
            response_content=(
                "É um lindo gato!\n<<<DESC_IMAGEM>>>\nUm gato preto sobre o sofá."
            ),
        )

        result = captured["result"]
        assert set(result.keys()) >= {"output", "image_description"}
        assert result["output"] == "É um lindo gato!"
        assert result["image_description"] == "Um gato preto sobre o sofá."
        assert "<<<DESC_IMAGEM>>>" not in result["output"]
        assert "Um gato preto sobre o sofá." not in result["output"]

    def test_missing_marker_with_image__fallback_description(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="o que é isso?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        captured = _invoke_capturing(
            graph, request, response_content="É um lindo gato, sem marcador!"
        )

        result = captured["result"]
        assert result["output"] == "É um lindo gato, sem marcador!"
        assert result["image_description"] == "[imagem enviada]"

    def test_marker_directive_injected_only_with_image(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(
            message="o que é isso?", user=_sample_user(), images=[VALID_PNG], user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        assert "<<<DESC_IMAGEM>>>" in captured["system"]

    def test_marker_directive_absent_without_image(self):
        history = _make_history()
        graph = _make_graph(MagicMock(return_value=history))
        request = GraphInvokeRequest(message="oi", user=_sample_user(), user_timezone=_TZ)

        captured = _invoke_capturing(graph, request)

        assert "<<<DESC_IMAGEM>>>" not in captured["system"]

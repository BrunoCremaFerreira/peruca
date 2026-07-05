"""
OnlyTalkGraph on-demand re-vision unit tests (TDD - RED phase, Fase C).

A text follow-up may need a concrete visual detail the stored description does
not cover. The first (cheap) pass may then emit the sentinel
``<<<REVER_IMAGEM: #N | mais_recente>>>``; the graph resolves the base64 from
the ImageStore (always in the request user's scope) and runs a second pass with
the image re-injected as a multimodal content block, producing an updated
description.

Safeguards:
  - no ImageStore, or no stored blob for the target → the sentinel is a no-op
    (stripped from the answer; single pass);
  - the store is accessed through its synchronous facade (no asyncio.run in the
    node);
  - the target id is always resolved within ``user.id`` (cross-user isolation).

Expected to FAIL until OnlyTalkGraph gains the re-vision gate.
"""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


_PROMPT_TEMPLATE = "{user_name}|{user_summary}|{user_memories}|{current_datetime}"
SECOND_URI = "data:image/png;base64,U0VDT05E"


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _history_with_image(handle="3"):
    return [HumanMessage(content=f"[Imagem #{handle} enviada pelo usuário: um documento]")]


def _make_graph(image_store=None, history=None):
    llm_chat = MagicMock()
    get_session_history = MagicMock(return_value=MagicMock(messages=history or []))
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        graph = OnlyTalkGraph(
            llm_chat=llm_chat,
            get_session_history=get_session_history,
            image_store=image_store,
        )
    return graph


def _invoke_with_passes(graph, request, responses):
    """Short-circuit the chain, feeding one queued response.content per pass."""
    captured = {"passes": [], "systems": []}
    resp_iter = iter(responses)

    def make_chain():
        chain = MagicMock()

        def inv(payload, *a, **k):
            r = MagicMock()
            r.content = next(resp_iter)
            captured["passes"].append({"input": payload, "content": r.content})
            return r

        chain.invoke.side_effect = inv
        return chain

    def fake_from_messages(messages):
        captured["systems"].append(messages[0][1])
        prompt_mock = MagicMock()
        prompt_mock.__or__.return_value = make_chain()
        return prompt_mock

    with patch(
        "application.graphs.only_talk_graph.ChatPromptTemplate.from_messages",
        side_effect=fake_from_messages,
    ):
        captured["result"] = graph.invoke(request)
    return captured


class TestOnlyTalkGraphRevision:
    def test_explicit_handle__triggers_get_and_second_pass_with_image(self):
        user = _sample_user()
        store = MagicMock()
        store.get.return_value = SECOND_URI
        graph = _make_graph(image_store=store, history=_history_with_image("3"))
        request = GraphInvokeRequest(
            message="qual o número de série na foto?", user=user, images=[]
        )

        captured = _invoke_with_passes(
            graph,
            request,
            responses=[
                "Deixa eu olhar melhor.\n<<<REVER_IMAGEM: #3>>>",
                "O número é XYZ-123.\n<<<DESC_IMAGEM>>>\nDocumento com o número de série XYZ-123 no topo.",
            ],
        )

        # resolved strictly within the request user's scope
        store.get.assert_called_once_with(user.id, "3")
        # two passes ran; the second carried a multimodal image block
        assert len(captured["passes"]) == 2
        second_content = captured["passes"][1]["input"]["input"][0].content
        assert any(b.get("type") == "image_url" for b in second_content)
        assert SECOND_URI in str(second_content)

        result = captured["result"]
        assert result["output"] == "O número é XYZ-123."
        assert "XYZ-123" in result["image_description"]
        assert result["revised_image_index"] == "3"
        assert "<<<" not in result["output"]

    def test_latest__uses_latest_id_then_get(self):
        user = _sample_user()
        store = MagicMock()
        store.latest_id.return_value = "5"
        store.get.return_value = SECOND_URI
        graph = _make_graph(image_store=store, history=_history_with_image("5"))
        request = GraphInvokeRequest(message="e a cor exata?", user=user, images=[])

        captured = _invoke_with_passes(
            graph,
            request,
            responses=[
                "Deixe-me ver.\n<<<REVER_IMAGEM: mais_recente>>>",
                "É azul-marinho.\n<<<DESC_IMAGEM>>>\nCamisa azul-marinho.",
            ],
        )

        store.latest_id.assert_called_once_with(user.id)
        store.get.assert_called_once_with(user.id, "5")
        assert captured["result"]["revised_image_index"] == "5"

    def test_no_stored_blob__sentinel_is_noop(self):
        user = _sample_user()
        store = MagicMock()
        store.get.return_value = None
        store.latest_id.return_value = None
        graph = _make_graph(image_store=store, history=_history_with_image("3"))
        request = GraphInvokeRequest(message="qual o número?", user=user, images=[])

        captured = _invoke_with_passes(
            graph,
            request,
            responses=["Não tenho certeza.\n<<<REVER_IMAGEM: mais_recente>>>"],
        )

        assert len(captured["passes"]) == 1
        result = captured["result"]
        assert result["output"] == "Não tenho certeza."
        assert "<<<REVER_IMAGEM" not in result["output"]
        assert result["revised_image_index"] is None

    def test_no_store__sentinel_stripped_no_crash(self):
        user = _sample_user()
        graph = _make_graph(image_store=None, history=_history_with_image("1"))
        request = GraphInvokeRequest(message="qual o número?", user=user, images=[])

        captured = _invoke_with_passes(
            graph, request, responses=["Bla bla.\n<<<REVER_IMAGEM: #1>>>"]
        )

        assert len(captured["passes"]) == 1
        assert captured["result"]["output"] == "Bla bla."
        assert "<<<" not in captured["result"]["output"]

    def test_store_accessed_synchronously_not_via_asyncio_run(self):
        user = _sample_user()
        store = MagicMock()
        store.get.return_value = SECOND_URI
        graph = _make_graph(image_store=store, history=_history_with_image("2"))
        request = GraphInvokeRequest(message="qual o texto?", user=user, images=[])

        with patch.object(asyncio, "run") as async_run:
            _invoke_with_passes(
                graph,
                request,
                responses=[
                    "Vendo.\n<<<REVER_IMAGEM: #2>>>",
                    "Diz 'saída'.\n<<<DESC_IMAGEM>>>\nPlaca escrita saída.",
                ],
            )

        async_run.assert_not_called()

    def test_no_sentinel__single_pass_plain_answer(self):
        user = _sample_user()
        store = MagicMock()
        graph = _make_graph(image_store=store, history=_history_with_image("1"))
        request = GraphInvokeRequest(message="tudo bem?", user=user, images=[])

        captured = _invoke_with_passes(graph, request, responses=["Tudo ótimo!"])

        assert len(captured["passes"]) == 1
        assert captured["result"]["output"] == "Tudo ótimo!"
        assert captured["result"]["revised_image_index"] is None
        store.get.assert_not_called()

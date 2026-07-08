"""
OnlyTalkGraph history windowing (fix do truncamento).

Bug: OnlyTalkGraph injetava o histórico INTEIRO no prompt. Numa conversa longa
(ex.: 130 mensagens) o prompt se aproxima/estoura o num_ctx e a geração para no
meio da frase (done_reason=length). A correção janela o histórico às últimas N
mensagens, preservando ordem e deixando orçamento para a geração.
"""

import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from application.graphs.only_talk_graph import OnlyTalkGraph
from domain.entities import GraphInvokeRequest, User


_PROMPT_TEMPLATE = "{user_name}|{user_summary}|{user_memories}|{siblings}|{current_datetime}"


def _user():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Bruno", summary="")


def _history(n):
    msgs = []
    for i in range(n):
        msgs.append(HumanMessage(content=f"pergunta {i}"))
        msgs.append(AIMessage(content=f"resposta {i}"))
    return msgs


def _make_graph(get_session_history, history_max_messages=None):
    with patch.object(OnlyTalkGraph, "load_prompt", return_value=_PROMPT_TEMPLATE):
        return OnlyTalkGraph(
            llm_chat=MagicMock(),
            get_session_history=get_session_history,
            history_max_messages=history_max_messages,
        )


def _capture_history(graph, request):
    captured = {}
    response = MagicMock()
    response.content = "resposta"
    chain_mock = MagicMock()

    def fake_invoke(payload, *a, **k):
        captured["input"] = payload
        return response

    chain_mock.invoke.side_effect = fake_invoke

    def fake_from_messages(messages):
        p = MagicMock()
        p.__or__.return_value = chain_mock
        return p

    with patch(
        "application.graphs.only_talk_graph.ChatPromptTemplate.from_messages",
        side_effect=fake_from_messages,
    ):
        graph.invoke(request)
    return captured["input"]["history"]


class TestHistoryWindow:
    def test_long_history_is_windowed_to_last_n(self):
        messages = _history(65)  # 130 messages
        get_hist = lambda _uid: MagicMock(messages=messages)
        graph = _make_graph(get_hist, history_max_messages=20)

        injected = _capture_history(
            graph, GraphInvokeRequest(message="oi", user=_user(), context_hints={})
        )

        assert len(injected) == 20
        # Keeps the MOST RECENT messages, in order.
        assert injected == messages[-20:]

    def test_short_history_passes_through(self):
        messages = _history(3)  # 6 messages
        get_hist = lambda _uid: MagicMock(messages=messages)
        graph = _make_graph(get_hist, history_max_messages=20)

        injected = _capture_history(
            graph, GraphInvokeRequest(message="oi", user=_user(), context_hints={})
        )
        assert injected == messages

    def test_none_limit_keeps_full_history(self):
        messages = _history(50)
        get_hist = lambda _uid: MagicMock(messages=messages)
        graph = _make_graph(get_hist, history_max_messages=None)

        injected = _capture_history(
            graph, GraphInvokeRequest(message="oi", user=_user(), context_hints={})
        )
        assert len(injected) == 100

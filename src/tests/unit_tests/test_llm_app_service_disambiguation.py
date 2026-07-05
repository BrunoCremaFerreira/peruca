"""
LlmAppService disambiguation consumption (TDD — written before implementation).

When a pending disambiguation exists for the user, chat() must resolve the
follow-up reply BEFORE invoking the main graph:

  - match  -> apply the stored operation on the chosen candidate id via
              shopping_list_service, clear the pending, and answer directly
              (the MainGraph is NOT invoked — no extra LLM cost).
  - cancel -> clear the pending, answer a short confirmation, do not invoke
              the MainGraph.
  - none   -> clear the pending and fall through to the MainGraph with the
              original message (do not trap the user in a loop).

New constructor params (both optional, default None):
    LlmAppService(..., shopping_list_service=None, disambiguation_service=None)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import DisambiguationCandidate, PendingDisambiguation, User
from domain.services.disambiguation_service import ChoiceResult


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _make_service(user, pending, resolve_result=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "ok", "intent": ["only_talking"]}

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    shopping_list_service = MagicMock()

    disambiguation_service = MagicMock()
    disambiguation_service.get_pending = AsyncMock(return_value=pending)
    disambiguation_service.clear_pending = AsyncMock()
    disambiguation_service.resolve_choice = MagicMock(return_value=resolve_result)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        shopping_list_service=shopping_list_service,
        disambiguation_service=disambiguation_service,
    )
    return service, main_graph, shopping_list_service, disambiguation_service


def _pending(operation="delete"):
    return PendingDisambiguation(
        operation=operation,
        query="carne",
        candidates=[
            DisambiguationCandidate(id="p-id", name="Carne de panela"),
            DisambiguationCandidate(id="s-id", name="Carne seca"),
        ],
    )


def _request(user, message):
    return ChatRequest(message=message, external_user_id=user.external_id, chat_id="c1")


class TestDisambiguationMatch:
    def test_delete_match__applies_delete_clears_and_skips_main_graph(self):
        user = _sample_user()
        chosen = DisambiguationCandidate(id="p-id", name="Carne de panela")
        service, main_graph, shopping, disambig = _make_service(
            user, _pending("delete"), ChoiceResult(kind="match", candidate=chosen)
        )

        result = service.chat(_request(user, "a primeira"))

        shopping.delete.assert_called_once_with("p-id")
        disambig.clear_pending.assert_called_once()
        main_graph.invoke.assert_not_called()
        assert "Carne de panela" in result["output"]

    def test_check_match__applies_check(self):
        user = _sample_user()
        chosen = DisambiguationCandidate(id="p-id", name="Carne de panela")
        service, main_graph, shopping, disambig = _make_service(
            user, _pending("check"), ChoiceResult(kind="match", candidate=chosen)
        )

        service.chat(_request(user, "carne de panela"))

        shopping.check.assert_called_once_with("p-id")
        shopping.delete.assert_not_called()
        main_graph.invoke.assert_not_called()

    def test_uncheck_match__applies_uncheck(self):
        user = _sample_user()
        chosen = DisambiguationCandidate(id="s-id", name="Carne seca")
        service, main_graph, shopping, disambig = _make_service(
            user, _pending("uncheck"), ChoiceResult(kind="match", candidate=chosen)
        )

        service.chat(_request(user, "a segunda"))

        shopping.uncheck.assert_called_once_with("s-id")
        main_graph.invoke.assert_not_called()


class TestDisambiguationCancel:
    def test_cancel__clears_and_skips_main_graph(self):
        user = _sample_user()
        service, main_graph, shopping, disambig = _make_service(
            user, _pending("delete"), ChoiceResult(kind="cancel")
        )

        result = service.chat(_request(user, "cancelar"))

        disambig.clear_pending.assert_called_once()
        shopping.delete.assert_not_called()
        main_graph.invoke.assert_not_called()
        assert isinstance(result["output"], str) and result["output"].strip()


class TestDisambiguationNoneFallsThrough:
    def test_none__clears_and_falls_through_to_main_graph(self):
        user = _sample_user()
        service, main_graph, shopping, disambig = _make_service(
            user, _pending("delete"), ChoiceResult(kind="none")
        )

        service.chat(_request(user, "acende a luz da sala"))

        disambig.clear_pending.assert_called_once()
        shopping.delete.assert_not_called()
        main_graph.invoke.assert_called_once()
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.message == "acende a luz da sala"


class TestNoPending:
    def test_no_pending__normal_flow_invokes_main_graph(self):
        user = _sample_user()
        service, main_graph, shopping, disambig = _make_service(
            user, pending=None
        )

        service.chat(_request(user, "oi"))

        main_graph.invoke.assert_called_once()
        disambig.resolve_choice.assert_not_called()

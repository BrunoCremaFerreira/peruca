"""
UserSettingsGraph handler unit tests (TDD RED — plan §10.5).

The action nodes are 100% deterministic: they consume what classify already put
in the state and NEVER call the LLM (mould: test_pet_health_graph_handlers.py).

Contract fixed by these tests:

    _handle_set_timezone(state)      -> {"output_set": str}
    _handle_get_timezone(state)      -> {"output_get": str}
    _handle_not_recognized(state)    -> {"output_not_recognized": str}
    _handle_final_response(state)    -> {"output": str}   (deterministic merge)

    * set persists the ALREADY-RESOLVED identifier:
      user_settings_service.set_timezone(user.id, "America/Sao_Paulo")
    * an unresolved location never persists anything and answers with the
      anchored, example-bearing message of §3.5;
    * get reads user_settings_service.get_timezone(user.id) and echoes it.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User
from domain.exceptions import ValidationError

pytest.importorskip("langgraph")

from application.graphs.user_settings_graph import UserSettingsGraph


_TZ = "America/Sao_Paulo"
_EXAMPLE_CITIES = ("São Paulo", "Lisboa", "Nova York", "Londres")


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _make_repo(current_timezone=_TZ):
    service = MagicMock()
    service.get_timezone.return_value = current_timezone
    return service


def _make_graph(user_settings_service=None):
    with patch.object(UserSettingsGraph, "load_prompt", return_value="{input}"):
        graph = UserSettingsGraph(
            llm_chat=MagicMock(),
            user_settings_service=user_settings_service or _make_repo(),
        )
    return graph


def _req(user, message="msg"):
    return GraphInvokeRequest(message=message, user=user, user_timezone=_TZ)


def _set_state(user, resolved_timezone, location="São Paulo"):
    return {
        "input": _req(user),
        "intent": ["set_timezone"],
        "location": location,
        "timezone_iana": "",
        "resolved_timezone": resolved_timezone,
    }


class TestSetTimezoneNode:
    def test_set__persists_resolved_iana(self):
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        out = graph._handle_set_timezone(_set_state(user, "America/Sao_Paulo"))
        service.set_timezone.assert_called_once_with(user.id, "America/Sao_Paulo")
        assert "America/Sao_Paulo" in out["output_set"]

    def test_set__llm_not_called_in_action_node(self):
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        graph._handle_set_timezone(_set_state(user, "Europe/Lisbon", location="Lisboa"))
        graph.llm_chat.invoke.assert_not_called()
        graph.llm_chat.assert_not_called()

    def test_unknown_city__friendly_message_no_persistence(self):
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        out = graph._handle_set_timezone(
            _set_state(user, None, location="Pindorama do Norte")
        )
        service.set_timezone.assert_not_called()
        message = out["output_set"]
        assert message and message.strip()
        # Anchored with real examples (§3.5 item 3), not a request for an IANA id.
        assert any(city in message for city in _EXAMPLE_CITIES)

    def test_unknown_city__does_not_call_the_llm_either(self):
        user = _user()
        graph = _make_graph()
        graph._handle_set_timezone(_set_state(user, None, location="???"))
        graph.llm_chat.invoke.assert_not_called()

    def test_set__service_rejects_timezone__reports_without_crashing(self):
        # Defence in depth: the service validates again. A ValidationError must
        # become a friendly answer, never a 500.
        user = _user()
        service = _make_repo()
        service.set_timezone.side_effect = ValidationError(["Invalid timezone"])
        graph = _make_graph(service)
        out = graph._handle_set_timezone(_set_state(user, "America/Sao_Paulo"))
        assert out["output_set"] and out["output_set"].strip()


class TestGetTimezoneNode:
    def test_get__returns_configured_tz_no_llm(self):
        user = _user()
        service = _make_repo(current_timezone="Europe/Lisbon")
        graph = _make_graph(service)
        out = graph._handle_get_timezone({"input": _req(user), "intent": ["get_timezone"]})
        service.get_timezone.assert_called_once_with(user.id)
        assert "Europe/Lisbon" in out["output_get"]
        graph.llm_chat.invoke.assert_not_called()

    def test_get__never_writes(self):
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        graph._handle_get_timezone({"input": _req(user), "intent": ["get_timezone"]})
        service.set_timezone.assert_not_called()


class TestNotRecognizedNode:
    def test_not_recognized__returns_message_without_llm(self):
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        out = graph._handle_not_recognized({"input": _req(user)})
        assert isinstance(out["output_not_recognized"], str)
        assert out["output_not_recognized"].strip()
        graph.llm_chat.invoke.assert_not_called()
        service.set_timezone.assert_not_called()


class TestFinalResponse:
    def test_single_output__passed_through_verbatim(self):
        graph = _make_graph()
        out = graph._handle_final_response(
            {"input": _req(_user()), "output_set": "Pronto! Agora uso o fuso de X."}
        )
        assert out["output"] == "Pronto! Agora uso o fuso de X."

    def test_final_response__does_not_call_the_llm(self):
        graph = _make_graph()
        graph._handle_final_response(
            {"input": _req(_user()), "output_get": "Estou usando o fuso Y."}
        )
        graph.llm_chat.invoke.assert_not_called()

    def test_no_output__empty_string(self):
        graph = _make_graph()
        out = graph._handle_final_response({"input": _req(_user())})
        assert out["output"] == ""

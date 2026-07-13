"""
UserSettingsGraph classify unit tests (TDD RED — plan §10.5) — LLM mocked.

Contract fixed by these tests (mould: test_pet_health_graph_classify_intent.py):

    application/graphs/user_settings_graph.py

    class UserSettingsGraph(Graph):
        def __init__(self, llm_chat, user_settings_service,
                     provider="OLLAMA", strip_think_directive=False)

    Prompt: infra/prompts/user_settings_graph.md (single {input} slot).

    The classify node makes the ONLY LLM call of the graph. The model emits JSON
    parsed with json.loads() via Graph._extract_structured_output():

        {"intents": ["set_timezone"], "location": "São Paulo",
         "timezone_iana": "America/Sao_Paulo"}

    Python — never the LLM — is the authority on the identifier: the classify node
    runs domain.services.timezone_resolver.resolve_timezone(location=...,
    timezone_iana=...) and parks the result in state["resolved_timezone"] (None
    when nothing resolves with certainty). A hallucinated IANA is discarded and
    the location is used instead.

    State keys produced: intent, input, location, timezone_iana,
    resolved_timezone.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User

pytest.importorskip("langgraph")

from application.graphs.user_settings_graph import UserSettingsGraph


_TZ = "America/Sao_Paulo"


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _make_repo(current_timezone=_TZ):
    """A UserSettingsService test double (the graph never sees a repository)."""
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


def _classify(graph, user, raw_json, message="msg"):
    req = GraphInvokeRequest(message=message, user=user, user_timezone=_TZ)
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": req})


class TestClassify:
    def test_set_timezone_with_city__resolves_iana_in_state(self):
        user = _user()
        graph = _make_graph()
        raw = (
            '{"intents": ["set_timezone"], "location": "São Paulo", '
            '"timezone_iana": "America/Sao_Paulo"}'
        )
        state = _classify(graph, user, raw, message="altere o timezone para São Paulo")
        assert state["intent"] == ["set_timezone"]
        assert state["resolved_timezone"] == "America/Sao_Paulo"

    def test_city_only__no_iana_from_llm__resolved_from_location(self):
        # The most important few-shot (§6): the model is honest about not knowing
        # the identifier and Python resolves the spoken city.
        user = _user()
        graph = _make_graph()
        raw = '{"intents": ["set_timezone"], "location": "Lisboa", "timezone_iana": ""}'
        state = _classify(graph, user, raw, message="muda o fuso para Lisboa")
        assert state["intent"] == ["set_timezone"]
        assert state["resolved_timezone"] == "Europe/Lisbon"

    def test_unknown_city__state_has_no_resolution(self):
        # Intent is preserved (the handler answers with a friendly message);
        # the resolver never guesses.
        user = _user()
        graph = _make_graph()
        raw = (
            '{"intents": ["set_timezone"], "location": "Pindorama do Norte", '
            '"timezone_iana": ""}'
        )
        state = _classify(graph, user, raw)
        assert state["intent"] == ["set_timezone"]
        assert state["resolved_timezone"] is None

    def test_hallucinated_iana__discarded_falls_back_to_location(self):
        # "America/Lisboa" does not exist in the tz database: Python is the
        # authority, so the identifier is dropped and the location wins.
        user = _user()
        graph = _make_graph()
        raw = (
            '{"intents": ["set_timezone"], "location": "Lisboa", '
            '"timezone_iana": "America/Lisboa"}'
        )
        state = _classify(graph, user, raw)
        assert state["resolved_timezone"] == "Europe/Lisbon"

    def test_hallucinated_iana_and_unknown_location__no_resolution(self):
        user = _user()
        graph = _make_graph()
        raw = (
            '{"intents": ["set_timezone"], "location": "Rondonópolis", '
            '"timezone_iana": "America/Rondonopolis"}'
        )
        state = _classify(graph, user, raw)
        assert state["resolved_timezone"] is None

    def test_get_timezone_intent__classified(self):
        user = _user()
        graph = _make_graph()
        raw = '{"intents": ["get_timezone"], "location": "", "timezone_iana": ""}'
        state = _classify(graph, user, raw, message="qual timezone está configurado?")
        assert state["intent"] == ["get_timezone"]
        assert state["resolved_timezone"] is None

    def test_malformed_json__falls_back_to_not_recognized(self):
        user = _user()
        graph = _make_graph()
        state = _classify(graph, user, "não é json")
        assert state["intent"] == ["not_recognized"]

    def test_none_extract__falls_back_to_not_recognized(self):
        user = _user()
        graph = _make_graph()
        state = _classify(graph, user, None)
        assert state["intent"] == ["not_recognized"]

    def test_not_recognized_intent__classified(self):
        user = _user()
        graph = _make_graph()
        raw = '{"intents": ["not_recognized"], "location": "", "timezone_iana": ""}'
        state = _classify(graph, user, raw, message="que horas são?")
        assert state["intent"] == ["not_recognized"]

    def test_classify__does_not_touch_the_settings_service(self):
        # Reading/writing settings belongs to the action nodes.
        user = _user()
        service = _make_repo()
        graph = _make_graph(service)
        raw = (
            '{"intents": ["set_timezone"], "location": "São Paulo", '
            '"timezone_iana": "America/Sao_Paulo"}'
        )
        _classify(graph, user, raw)
        service.set_timezone.assert_not_called()
        service.get_timezone.assert_not_called()

    def test_classify__keeps_the_request_in_state(self):
        user = _user()
        graph = _make_graph()
        raw = '{"intents": ["get_timezone"], "location": "", "timezone_iana": ""}'
        state = _classify(graph, user, raw)
        assert state["input"].user.id == user.id

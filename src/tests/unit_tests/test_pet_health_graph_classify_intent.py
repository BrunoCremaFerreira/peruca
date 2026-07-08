"""
PetHealthGraph classify unit tests (TDD) — LLM mocked.

The classifier emits JSON (json.loads); the node parses intents + slots, resolves
the dictated date via date_resolver and the pet term in Python. Malformed output
falls back to not_recognized.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, Pet, User

pytest.importorskip("langgraph")

from application.graphs.pet_health_graph import PetHealthGraph


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _pets(user_id):
    return [
        Pet(id="id-caco", user_id=user_id, name="Caçolin", nicknames=["Lilo", "Suzu"]),
        Pet(id="id-cacao", user_id=user_id, name="Caçolão", nicknames=["Lyon"]),
    ]


def _make_graph(pets):
    with patch.object(PetHealthGraph, "load_prompt", return_value="{input}"):
        pet_read_repo = MagicMock()
        pet_read_repo.get_all_by_user_id.return_value = pets
        graph = PetHealthGraph(
            llm_chat=MagicMock(),
            pet_read_repository=pet_read_repo,
            pet_health_service=MagicMock(),
            pet_health_flow_service=MagicMock(),
            get_session_history=None,
        )
    return graph


def _classify(graph, user, raw_json):
    req = GraphInvokeRequest(message="msg", user=user)
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": req})


class TestClassify:
    def test_register_with_token_date_resolves(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = (
            '{"intents": ["register_health_event"], "pet_term": "caçolin", '
            '"event_type": "vaccine", "event_name": "DHPPI", "date_token": "today", '
            '"date_value": "", "period": "", "query": "", "query_kind": "", '
            '"query_limit": 0, "edit_field": "", "new_value": ""}'
        )
        state = _classify(graph, user, raw)
        assert state["intent"] == ["register_health_event"]
        assert state["resolved_occurred_at"] == date.today()
        assert state["event_type"] == "vaccine"
        assert len(state["matched_pets"]) == 1
        assert state["matched_pets"][0].id == "id-caco"

    def test_matched_by_nickname(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = (
            '{"intents": ["register_health_event"], "pet_term": "Lyon", '
            '"event_type": "vaccine", "event_name": "raiva", "date_token": "yesterday"}'
        )
        state = _classify(graph, user, raw)
        assert state["resolved_occurred_at"] == date.today() - timedelta(days=1)
        assert len(state["matched_pets"]) == 1
        assert state["matched_pets"][0].id == "id-cacao"

    def test_explicit_date(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = (
            '{"intents": ["register_health_event"], "pet_term": "caçolão", '
            '"event_type": "dewormer", "event_name": "Bravecto", "date_value": "2026-05-12"}'
        )
        state = _classify(graph, user, raw)
        assert state["resolved_occurred_at"] == date(2026, 5, 12)

    def test_list_pets(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = '{"intents": ["list_pets"], "pet_term": ""}'
        state = _classify(graph, user, raw)
        assert state["intent"] == ["list_pets"]

    def test_write_forbidden(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = '{"intents": ["pet_write_forbidden"], "pet_term": "Mel"}'
        state = _classify(graph, user, raw)
        assert state["intent"] == ["pet_write_forbidden"]

    def test_malformed_json__not_recognized(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        state = _classify(graph, user, "not json")
        assert state["intent"] == ["not_recognized"]

    def test_none_extract__not_recognized(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        state = _classify(graph, user, None)
        assert state["intent"] == ["not_recognized"]

    def test_query_carries_period_and_kind(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        raw = (
            '{"intents": ["query_health_event"], "pet_term": "caçolin", '
            '"event_name": "gripe canina", "period": "this_year", '
            '"query": "já tomou", "query_kind": "open", "query_limit": 0}'
        )
        state = _classify(graph, user, raw)
        assert state["intent"] == ["query_health_event"]
        assert state["query_kind"] == "open"
        assert state["resolved_period"] is not None

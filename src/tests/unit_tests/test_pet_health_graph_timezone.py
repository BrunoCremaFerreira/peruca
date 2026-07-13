"""
PetHealthGraph timezone plumbing (TDD RED — plan §8.3 / §10.6).

Mirror of test_vehicle_maintenance_graph_timezone.py: every `date.today()` in the
graph becomes `local_date_for_user(request.user_timezone)` — the reference given
to `resolve_date_token` / `resolve_period` / `parse_explicit_date` and to the
`current_date` slot of the prompt.

`occurred_at` itself is a CIVIL date (§3.6): never converted, only its reference
moves.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, Pet, User
from domain.exceptions import ValidationError

pytest.importorskip("langgraph")

from application.graphs.pet_health_graph import PetHealthGraph


_SP = "America/Sao_Paulo"
_FAR_EAST = "Pacific/Kiritimati"  # UTC+14
_FAR_WEST = "Pacific/Midway"  # UTC-11


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _pets(user_id):
    return [Pet(id="id-caco", user_id=user_id, name="Caçolin", nicknames=["Lilo"])]


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


def _req(user, user_timezone=_SP, message="msg"):
    return GraphInvokeRequest(message=message, user=user, user_timezone=user_timezone)


def _capture_payload(graph):
    response = MagicMock()
    response.content = "{}"
    chain = MagicMock()
    chain.invoke.return_value = response
    prompt = MagicMock()
    prompt.__or__.return_value = chain
    graph.classification_prompt = prompt
    return chain


def _classify(graph, request, raw_json):
    with patch.object(graph, "_extract_structured_output", return_value=raw_json):
        return graph._classify_intent({"input": request})


_TODAY = (
    '{"intents": ["register_health_event"], "pet_term": "caçolin", '
    '"event_type": "vaccine", "event_name": "DHPPI", "date_token": "today"}'
)
_YESTERDAY = (
    '{"intents": ["register_health_event"], "pet_term": "caçolin", '
    '"event_type": "vaccine", "event_name": "raiva", "date_token": "yesterday"}'
)


class TestClassifyReferenceDate:
    def test_current_date_slot__is_the_user_local_date(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        chain = _capture_payload(graph)
        with patch(
            "application.graphs.pet_health_graph.local_date_for_user",
            return_value=date(2026, 7, 9),
        ) as local_date:
            _classify(graph, _req(user), _TODAY)
        local_date.assert_called()
        assert local_date.call_args[0][0] == _SP
        payload = chain.invoke.call_args[0][0]
        assert payload["current_date"] == "2026-07-09"

    def test_midnight_edge__token_resolves_against_the_user_day(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        _capture_payload(graph)
        with patch(
            "application.graphs.pet_health_graph.local_date_for_user",
            return_value=date(2026, 7, 9),
        ):
            state = _classify(graph, _req(user), _TODAY)
        assert state["resolved_occurred_at"] == date(2026, 7, 9)

    def test_yesterday_token__relative_to_the_user_day(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        _capture_payload(graph)
        frozen = date(2026, 7, 9)
        with patch(
            "application.graphs.pet_health_graph.local_date_for_user",
            return_value=frozen,
        ):
            state = _classify(graph, _req(user), _YESTERDAY)
        assert state["resolved_occurred_at"] == frozen - timedelta(days=1)

    def test_two_distant_timezones__resolve_to_different_days(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        _capture_payload(graph)
        east = _classify(graph, _req(user, _FAR_EAST), _TODAY)
        west = _classify(graph, _req(user, _FAR_WEST), _TODAY)
        assert east["resolved_occurred_at"] != west["resolved_occurred_at"]

    def test_empty_timezone__fails_loudly(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        _capture_payload(graph)
        with pytest.raises(ValidationError):
            _classify(graph, _req(user, ""), _TODAY)


class TestCivilDatesAreNotConverted:
    def test_explicit_date__stored_verbatim_whatever_the_timezone(self):
        user = _user()
        graph = _make_graph(_pets(user.id))
        _capture_payload(graph)
        raw = (
            '{"intents": ["register_health_event"], "pet_term": "caçolin", '
            '"event_type": "dewormer", "event_name": "Bravecto", '
            '"date_value": "2026-05-12"}'
        )
        east = _classify(graph, _req(user, _FAR_EAST), raw)
        west = _classify(graph, _req(user, _FAR_WEST), raw)
        assert east["resolved_occurred_at"] == date(2026, 5, 12)
        assert west["resolved_occurred_at"] == date(2026, 5, 12)

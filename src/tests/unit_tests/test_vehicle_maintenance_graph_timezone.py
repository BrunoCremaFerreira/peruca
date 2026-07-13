"""
VehicleMaintenanceGraph timezone plumbing (TDD RED — plan §8.2 / §10.6).

Today every date reference in the graph is `date.today()` — the SERVER's civil
date. It must become the USER's civil date:

    domain.services.clock.local_date_for_user(request.user_timezone)

and that reference is what feeds `resolve_date_token`, `resolve_period`,
`parse_explicit_date` and the `current_date` slot of the prompts.

What does NOT change (§3.6): `performed_at` is a CIVIL date (no time, no zone) —
it is stored and rendered as-is. Only the *reference* of "today"/"this_week"
moves to the user's timezone.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, User, Vehicle
from domain.exceptions import ValidationError

pytest.importorskip("langgraph")

from application.graphs.vehicle_maintenance_graph import VehicleMaintenanceGraph


_SP = "America/Sao_Paulo"
# 25 hours apart: at ANY instant these two timezones sit on different civil dates.
_FAR_EAST = "Pacific/Kiritimati"  # UTC+14
_FAR_WEST = "Pacific/Midway"  # UTC-11


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _fleet(user_id):
    return [
        Vehicle(
            id="id-out",
            user_id=user_id,
            name="Mitsubishi Outlander",
            brand="Mitsubishi",
            model="Outlander",
            year=2018,
        )
    ]


def _make_graph(fleet):
    with patch.object(VehicleMaintenanceGraph, "load_prompt", return_value="{input}"):
        vehicle_read_repo = MagicMock()
        vehicle_read_repo.get_all_by_user_id.return_value = fleet
        graph = VehicleMaintenanceGraph(
            llm_chat=MagicMock(),
            vehicle_read_repository=vehicle_read_repo,
            maintenance_service=MagicMock(),
            maintenance_flow_service=MagicMock(),
            get_session_history=None,
        )
    return graph


def _req(user, user_timezone=_SP, message="msg"):
    return GraphInvokeRequest(message=message, user=user, user_timezone=user_timezone)


def _capture_payload(graph):
    """Replace the classification chain, capturing the payload it is invoked with."""
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


_YESTERDAY = (
    '{"intents": ["register_maintenance"], "vehicle_term": "outlander", '
    '"description": "troca de óleo", "date_token": "yesterday", "odometer_km": 100232}'
)
_TODAY = (
    '{"intents": ["register_maintenance"], "vehicle_term": "outlander", '
    '"description": "troca de óleo", "date_token": "today", "odometer_km": 100232}'
)


class TestClassifyReferenceDate:
    def test_current_date_slot__is_the_user_local_date(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        chain = _capture_payload(graph)
        frozen = date(2026, 7, 9)
        with patch(
            "application.graphs.vehicle_maintenance_graph.local_date_for_user",
            return_value=frozen,
        ) as local_date:
            _classify(graph, _req(user), _TODAY)
        local_date.assert_called()
        assert local_date.call_args[0][0] == _SP
        payload = chain.invoke.call_args[0][0]
        assert payload["current_date"] == "2026-07-09"

    def test_midnight_edge__token_resolves_against_the_user_day(self):
        # 02:30Z in São Paulo is still the previous day: "today" must be the 9th,
        # not the server's 10th.
        user = _user()
        graph = _make_graph(_fleet(user.id))
        _capture_payload(graph)
        frozen = date(2026, 7, 9)
        with patch(
            "application.graphs.vehicle_maintenance_graph.local_date_for_user",
            return_value=frozen,
        ):
            state = _classify(graph, _req(user), _TODAY)
        assert state["resolved_performed_at"] == date(2026, 7, 9)

    def test_yesterday_token__relative_to_the_user_day(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        _capture_payload(graph)
        frozen = date(2026, 7, 9)
        with patch(
            "application.graphs.vehicle_maintenance_graph.local_date_for_user",
            return_value=frozen,
        ):
            state = _classify(graph, _req(user), _YESTERDAY)
        assert state["resolved_performed_at"] == frozen - timedelta(days=1)

    def test_two_distant_timezones__resolve_to_different_days(self):
        # Mock-free discriminating check: Kiritimati (UTC+14) and Midway (UTC-11)
        # are 25h apart, so their civil dates NEVER coincide. Under the old
        # `date.today()` both would resolve to the same day.
        user = _user()
        graph = _make_graph(_fleet(user.id))
        _capture_payload(graph)
        east = _classify(graph, _req(user, _FAR_EAST), _TODAY)
        west = _classify(graph, _req(user, _FAR_WEST), _TODAY)
        assert east["resolved_performed_at"] != west["resolved_performed_at"]

    def test_empty_timezone__fails_loudly(self):
        user = _user()
        graph = _make_graph(_fleet(user.id))
        _capture_payload(graph)
        with pytest.raises(ValidationError):
            _classify(graph, _req(user, ""), _TODAY)


class TestCivilDatesAreNotConverted:
    def test_explicit_date__stored_verbatim_whatever_the_timezone(self):
        # §3.6: performed_at is a civil date. Converting it would move the day.
        user = _user()
        graph = _make_graph(_fleet(user.id))
        _capture_payload(graph)
        raw = (
            '{"intents": ["register_maintenance"], "vehicle_term": "outlander", '
            '"description": "pneus", "date_value": "2020-01-10"}'
        )
        east = _classify(graph, _req(user, _FAR_EAST), raw)
        west = _classify(graph, _req(user, _FAR_WEST), raw)
        assert east["resolved_performed_at"] == date(2020, 1, 10)
        assert west["resolved_performed_at"] == date(2020, 1, 10)

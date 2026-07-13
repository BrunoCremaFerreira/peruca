"""
SmartHomeSensorsGraph timestamp timezone (TDD RED — plan §8.6 / §10.6).

THE most visible instance of the bug today (`smart_home_sensors_graph.py:173`):

    reading.last_changed.strftime("%H:%M")

`last_changed` comes from Home Assistant as a UTC datetime, so the history is
rendered in UTC — a reading from 22:00 in São Paulo is shown as "01:00". Unlike
`performed_at`/`occurred_at` (civil dates, never converted — §3.6), this IS a real
instant: it must be converted to the user's timezone before formatting, via
`domain.services.clock.format_local(dt, tz, "%H:%M")` / `to_local`.

The timezone travels in the request (`GraphInvokeRequest.user_timezone`), which the
graph already carries in `state["input"]`.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.entities import GraphInvokeRequest, SensorReading, SensorType, User
from domain.exceptions import ValidationError

pytest.importorskip("langgraph")

from application.graphs.smart_home_sensors_graph import SmartHomeSensorsGraph


_SP = "America/Sao_Paulo"
_TOKYO = "Asia/Tokyo"


def _uuid():
    return str(uuid.uuid4())


def _user():
    return User(id=_uuid(), external_id=_uuid(), name="Bruno")


def _sample_reading(last_changed):
    return SensorReading(
        entity_id="sensor.temp_sala",
        sensor_type=SensorType.TEMPERATURE,
        state="21.5",
        unit="°C",
        friendly_name="Temperatura Sala",
        last_changed=last_changed,
    )


def _make_graph(readings):
    with patch.object(SmartHomeSensorsGraph, "load_prompt", return_value="{input}"):
        service = MagicMock()
        service.sensor_get_history = AsyncMock(return_value=readings)
        alias_repository = MagicMock()
        alias_repository.get_all.return_value = []
        graph = SmartHomeSensorsGraph(
            llm_chat=MagicMock(),
            smart_home_service=service,
            smart_home_entity_alias_repository=alias_repository,
        )
    # Entity resolution is a separate LLM call and is not what this file tests.
    graph._find_entity_ids = MagicMock(return_value=["sensor.temp_sala"])
    return graph


def _state(user_timezone=_SP):
    return {
        "input": GraphInvokeRequest(
            message="como variou a temperatura da sala?",
            user=_user(),
            user_timezone=user_timezone,
        ),
        "output_query_history": "temperature|sala|3",
        "available_entities": {},
    }


class TestHistoryTimestampsInTheUserTimezone:
    def test_utc_reading__rendered_in_the_user_timezone(self):
        # 2026-07-10T01:00Z is 22:00 of the previous day in São Paulo.
        graph = _make_graph(
            [_sample_reading(datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc))]
        )
        out = graph._handle_query_history(_state(_SP))
        assert "22:00" in out["output_query_history"]
        assert "01:00" not in out["output_query_history"]

    def test_naive_timestamp_is_assumed_utc(self):
        # Nothing guarantees the adapter hands back an aware datetime; clock's
        # contract says naive == UTC.
        graph = _make_graph([_sample_reading(datetime(2026, 7, 10, 1, 0))])
        out = graph._handle_query_history(_state(_SP))
        assert "22:00" in out["output_query_history"]

    def test_same_instant_other_timezone__different_wall_clock(self):
        graph = _make_graph(
            [_sample_reading(datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc))]
        )
        out = graph._handle_query_history(_state(_TOKYO))
        assert "10:00" in out["output_query_history"]

    def test_missing_timestamp__still_renders_the_reading(self):
        graph = _make_graph([_sample_reading(None)])
        out = graph._handle_query_history(_state(_SP))
        assert "21.5" in out["output_query_history"]

    def test_empty_timezone__fails_loudly(self):
        graph = _make_graph(
            [_sample_reading(datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc))]
        )
        with pytest.raises(ValidationError):
            graph._handle_query_history(_state(""))

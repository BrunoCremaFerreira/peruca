"""
MainGraph classify_intent logging migration Unit Tests (TDD - RED phase).

Representative print -> logging site: the two fallback branches of
``MainGraph._classify_intent`` must emit ``logger.warning(...)`` on logger name
``"application.graphs.main_graph"`` instead of printing:
  - no extractable structure (``_extract_structured_output`` returns None);
  - the extracted literal fails ``eval()``.

Reuses the ``_make_main_graph`` / ``_sample_request`` construction pattern from
``test_main_graph_classify_intent.py``. Currently the code uses ``print(...)`` so
no record is captured -> RED via AssertionError.
"""

import logging
import uuid
from unittest.mock import MagicMock, patch

from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User

_LOGGER_NAME = "application.graphs.main_graph"


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _sample_request(message: str = "oi", context_hints: dict = None) -> GraphInvokeRequest:
    return GraphInvokeRequest(
        message=message,
        user=_sample_user(),
        memories=[],
        context_hints=context_hints or {},
    )


def _make_main_graph() -> MainGraph:
    llm_chat = MagicMock()
    llm_response = MagicMock()
    llm_response.content = '["only_talking"]'
    llm_chat.invoke.return_value = llm_response

    sub = MagicMock()
    sub.invoke.return_value = {"output": "ok"}

    with patch.object(MainGraph, "load_prompt", return_value="{input} {music_is_playing}"):
        return MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=sub,
            shopping_list_graph=sub,
            smart_home_lights_graph=sub,
            smart_home_climate_graph=sub,
            smart_home_sensors_graph=sub,
        )


def _warning_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == _LOGGER_NAME and r.levelno == logging.WARNING
    ]


# ===========================================================================
# TestMainGraphClassifyIntentLogging
# ===========================================================================


class TestMainGraphClassifyIntentLogging:
    def test_classify_intent__no_structure_found__logs_warning(self, caplog):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="não sei classificar isso")

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = graph._classify_intent({"input": _sample_request("???")})

        # Behaviour preserved: degrades to only_talking.
        assert result["intent"] == ["only_talking"], result
        assert _warning_records(caplog), (
            "expected a WARNING record on the no-structure fallback branch"
        )

    def test_classify_intent__eval_failed__logs_warning(self, caplog):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="[foo bar baz]")

        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = graph._classify_intent({"input": _sample_request("???")})

        # Behaviour preserved: degrades to only_talking.
        assert result["intent"] == ["only_talking"], result
        assert _warning_records(caplog), (
            "expected a WARNING record on the eval-failed fallback branch"
        )

    def test_classify_intent__no_structure_found__does_not_print(self, capsys):
        graph = _make_main_graph()
        graph._remove_thinking_tag = MagicMock(return_value="não sei classificar isso")

        graph._classify_intent({"input": _sample_request("???")})

        out = capsys.readouterr().out
        assert "fallback" not in out, (
            "the fallback branch must log instead of print to stdout"
        )

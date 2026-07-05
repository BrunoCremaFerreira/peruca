"""
LlmAppService logging migration Unit Tests (TDD - RED phase).

Representative print -> logging site: ``LlmAppService._persist_turn``. On failure
to persist the conversation turn, the ``except`` must emit
``logger.error(..., exc_info=True)`` on logger name
``"application.appservices.llm_app_service"`` WITHOUT propagating the exception
(current graceful-degradation contract preserved).

Currently the code uses ``print(...)``; these tests fail RED because no log
record is captured (AssertionError) and the anti-regression test still observes
the print on stdout.
"""

import logging
import uuid
from unittest.mock import MagicMock

from application.appservices.llm_app_service import LlmAppService
from domain.entities import User

_LOGGER_NAME = "application.appservices.llm_app_service"


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_service_with_failing_history() -> LlmAppService:
    """Build a service whose get_session_history factory raises inside _persist_turn."""

    def _failing_history(_user_id):
        raise RuntimeError("cache backend unreachable")

    return LlmAppService(
        main_graph=MagicMock(),
        context_repository=None,
        user_repository=MagicMock(),
        user_memory_service=MagicMock(),
        get_session_history=_failing_history,
    )


# ===========================================================================
# TestLlmAppServicePersistTurnLogging
# ===========================================================================


class TestLlmAppServicePersistTurnLogging:
    def test_persist_turn__history_raises__logs_error(self, caplog):
        service = _make_service_with_failing_history()
        user = _sample_user()

        with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
            service._persist_turn(user=user, message="oi", output="olá")

        error_records = [
            r
            for r in caplog.records
            if r.name == _LOGGER_NAME and r.levelno == logging.ERROR
        ]
        assert error_records, "expected an ERROR log record from _persist_turn except"

    def test_persist_turn__history_raises__logs_with_exc_info(self, caplog):
        service = _make_service_with_failing_history()
        user = _sample_user()

        with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
            service._persist_turn(user=user, message="oi", output="olá")

        error_records = [
            r
            for r in caplog.records
            if r.name == _LOGGER_NAME and r.levelno == logging.ERROR
        ]
        assert any(r.exc_info is not None for r in error_records), (
            "the persist-turn error log must capture the exception via exc_info=True"
        )

    def test_persist_turn__history_raises__does_not_propagate(self):
        service = _make_service_with_failing_history()
        user = _sample_user()

        # Must not raise (graceful degradation contract preserved).
        service._persist_turn(user=user, message="oi", output="olá")

    def test_persist_turn__history_raises__does_not_print(self, capsys):
        service = _make_service_with_failing_history()
        user = _sample_user()

        service._persist_turn(user=user, message="oi", output="olá")

        out = capsys.readouterr().out
        assert "Failed to persist turn" not in out, (
            "the except must log instead of print to stdout"
        )

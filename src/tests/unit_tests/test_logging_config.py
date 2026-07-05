"""
Unit tests for the structured logging bootstrap (TDD - RED phase).

Target module (not yet implemented): ``infra/logging_config.py`` exposing
``configure_logging(level: str | int) -> None``.

Fixed contract (agreed with arquiteto):
  - Acts on the ROOT logger.
  - Idempotent: every handler it adds is a ``logging.StreamHandler(sys.stdout)``
    tagged with the attribute ``_peruca = True``. On a subsequent call it removes
    ONLY the tagged handlers and adds exactly one — never touching foreign
    handlers (e.g. uvicorn's).
  - Format: ``"%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"`` with
    ISO-8601 datefmt ``"%Y-%m-%dT%H:%M:%S%z"``.
  - Applies the level via ``root.setLevel(level)``; accepts str and int; an
    invalid string level raises ``ValueError`` (native ``setLevel`` behaviour on
    3.12).

These tests import ``configure_logging`` lazily inside each test so the file
still COLLECTS cleanly while the module is absent; each test then fails RED with
``ImportError`` until the module exists.
"""

import logging
import sys

import pytest


# ===========================================================================
# Helpers / fixtures
# ===========================================================================


def _import_configure_logging():
    """Lazy import so collection succeeds pre-implementation (RED via ImportError)."""
    from infra.logging_config import configure_logging

    return configure_logging


def _peruca_handlers(root):
    return [h for h in root.handlers if getattr(h, "_peruca", False)]


@pytest.fixture
def restore_root_logger():
    """Snapshot and restore the root logger's handlers/level around each test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        yield root
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


# ===========================================================================
# TestConfigureLogging
# ===========================================================================


class TestConfigureLogging:
    def test_configure_logging__sets_level_on_root__level_applied(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("DEBUG")

        assert restore_root_logger.level == logging.DEBUG

    def test_configure_logging__accepts_int_level__level_applied(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging(logging.WARNING)

        assert restore_root_logger.level == logging.WARNING

    def test_configure_logging__adds_stream_handler_to_stdout__handler_present(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")

        handlers = _peruca_handlers(restore_root_logger)
        assert len(handlers) == 1
        handler = handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stdout

    def test_configure_logging__called_twice__does_not_duplicate_handler(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")
        configure_logging("INFO")

        assert len(_peruca_handlers(restore_root_logger)) == 1

    def test_configure_logging__called_twice__updates_level_without_new_handler(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")
        configure_logging("DEBUG")

        assert restore_root_logger.level == logging.DEBUG
        assert len(_peruca_handlers(restore_root_logger)) == 1

    def test_configure_logging__preserves_non_peruca_handlers(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()
        foreign = logging.NullHandler()  # stand-in for a uvicorn handler
        restore_root_logger.addHandler(foreign)

        configure_logging("INFO")
        configure_logging("INFO")

        assert foreign in restore_root_logger.handlers

    def test_configure_logging__sets_formatter__format_matches_contract(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")

        handler = _peruca_handlers(restore_root_logger)[0]
        formatter = handler.formatter
        assert formatter is not None
        assert formatter._fmt == "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        assert formatter.datefmt == "%Y-%m-%dT%H:%M:%S%z"

    def test_configure_logging__formatted_record__contains_expected_fields(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")

        handler = _peruca_handlers(restore_root_logger)[0]
        record = logging.LogRecord(
            name="application.example",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        rendered = handler.formatter.format(record)
        assert "INFO" in rendered
        assert "application.example" in rendered
        assert "hello world" in rendered

    def test_configure_logging__invalid_string_level__raises_value_error(
        self, restore_root_logger
    ):
        configure_logging = _import_configure_logging()

        with pytest.raises(ValueError):
            configure_logging("LOUD")

    def test_configure_logging__emitted_record_reaches_stdout(
        self, restore_root_logger, capsys
    ):
        configure_logging = _import_configure_logging()

        configure_logging("INFO")
        logging.getLogger("application.example").info("smoke-test-message")

        captured = capsys.readouterr().out
        assert "smoke-test-message" in captured

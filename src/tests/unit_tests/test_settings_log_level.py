"""
Settings.log_level Unit Tests (TDD - RED phase).

New field ``log_level: str`` on ``infra/settings.py``:
  - Default ``"INFO"``.
  - Read from env ``LOG_LEVEL``.
  - ``mode="before"`` validator: strip + upper; empty/blank -> ``"INFO"``;
    values outside {DEBUG, INFO, WARNING, ERROR, CRITICAL} rejected with a
    pydantic ``ValidationError``.

Mirrors the ``_settings_with_*`` / ``patch.dict(os.environ, clear=True)`` pattern
of ``test_settings.py``. Expected to fail RED with AttributeError (missing field)
until the field/validator exist.
"""

import os
from unittest.mock import patch

from pydantic import ValidationError
import pytest

from infra.settings import Settings

_LOG_LEVEL_KEY = "LOG_LEVEL"


def _settings_with_log_level(raw_value):
    """Instantiate Settings with LOG_LEVEL set to raw_value.

    A value of ``None`` removes the key entirely (simulating "unset").
    """
    env = dict(os.environ)
    env.pop(_LOG_LEVEL_KEY, None)
    if raw_value is not None:
        env[_LOG_LEVEL_KEY] = raw_value
    with patch.dict(os.environ, env, clear=True):
        return Settings()


class TestSettingsLogLevel:
    def test_log_level__unset__defaults_to_info(self):
        assert _settings_with_log_level(None).log_level == "INFO"

    def test_log_level__env_var_overrides__value_applied(self):
        assert _settings_with_log_level("DEBUG").log_level == "DEBUG"

    def test_log_level__lowercase_env__normalized_to_uppercase(self):
        assert _settings_with_log_level("debug").log_level == "DEBUG"

    def test_log_level__mixed_case_valid__normalized_to_uppercase(self):
        assert _settings_with_log_level("Warning").log_level == "WARNING"

    def test_log_level__whitespace_padded__stripped_and_normalized(self):
        assert _settings_with_log_level("  error  ").log_level == "ERROR"

    def test_log_level__empty_string__defaults_to_info(self):
        assert _settings_with_log_level("").log_level == "INFO"

    def test_log_level__blank_string__defaults_to_info(self):
        assert _settings_with_log_level("   ").log_level == "INFO"

    def test_log_level__invalid_value__raises_validation_error(self):
        with pytest.raises(ValidationError):
            _settings_with_log_level("verbose")

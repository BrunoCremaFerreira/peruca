"""
Settings Unit Tests

Focused on the parsing of CHAT_HISTORY_TTL_SECONDS, which is typed as
`int | None`. The shipped `.env.example` declares the key with an empty value
(`CHAT_HISTORY_TTL_SECONDS=`); without normalisation, pydantic raises a
ValidationError for an empty string, crashing Settings() construction. An
empty or blank value must be treated as "unset" (None).
"""

import os
from unittest.mock import patch

from infra.settings import Settings

_TTL_KEY = "CHAT_HISTORY_TTL_SECONDS"


def _settings_with_ttl(raw_value):
    """Instantiate Settings with CHAT_HISTORY_TTL_SECONDS set to raw_value.

    A value of ``None`` removes the key entirely (simulating "unset").
    """
    env = dict(os.environ)
    env.pop(_TTL_KEY, None)
    if raw_value is not None:
        env[_TTL_KEY] = raw_value
    with patch.dict(os.environ, env, clear=True):
        return Settings()


class TestChatHistoryTtlSeconds:
    def test_unset__defaults_to_none(self):
        assert _settings_with_ttl(None).chat_history_ttl_seconds is None

    def test_empty_string__normalised_to_none(self):
        # `.env.example` ships `CHAT_HISTORY_TTL_SECONDS=` — must not crash.
        assert _settings_with_ttl("").chat_history_ttl_seconds is None

    def test_blank_string__normalised_to_none(self):
        assert _settings_with_ttl("   ").chat_history_ttl_seconds is None

    def test_numeric_string__parsed_as_int(self):
        assert _settings_with_ttl("3600").chat_history_ttl_seconds == 3600

"""
Chat context compaction Settings unit tests — Phase A / F0 (TDD RED phase).

Drives the new fields added to `infra/settings.py` by the chat context
compaction plan (§4):

    # Chat context compaction (background summary of old turns)
    chat_compaction_enabled: bool = True
    chat_compaction_trigger_messages: int = 30    # fires when history >= this
    chat_compaction_trigger_chars: int = 24_000   # secondary trigger
    chat_compaction_keep_tail_messages: int = 16  # kept verbatim
    chat_compaction_max_summary_chars: int = 2_500

    llm_context_summary_graph_chat_model: str = "gemma4:12b"
    llm_context_summary_graph_chat_temperature: float = 0.2
    llm_context_summary_graph_chat_reasoning: bool | None = None

Contract driven here:
  1. Every field exists with the default above (a deployment that sets nothing
     gets compaction ON with the calibrated thresholds of §4).
  2. Every field is overridable through its upper-cased env var.
  3. Values are coerced to the declared type (env vars are always strings):
     "false"/"0" -> False, "12" -> 12, "0.5" -> 0.5.
  4. `llm_context_summary_graph_chat_reasoning` keeps the three-state semantics
     of the other graphs: unset -> None (inherit the global `llm_reasoning`),
     "true" -> True, "false" -> False.

Written BEFORE the implementation, so these tests are expected to FAIL RED with
AttributeError (the fields do not exist on Settings yet).

Mirrors the `_settings_with_*` + `patch.dict(os.environ, clear=True)` pattern of
test_settings.py / test_settings_log_level.py (no Settings mocking — the real
class is instantiated against a controlled environment).
"""

import os
from unittest.mock import patch

import pytest

from infra.settings import Settings


_COMPACTION_ENV_KEYS = (
    "CHAT_COMPACTION_ENABLED",
    "CHAT_COMPACTION_TRIGGER_MESSAGES",
    "CHAT_COMPACTION_TRIGGER_CHARS",
    "CHAT_COMPACTION_KEEP_TAIL_MESSAGES",
    "CHAT_COMPACTION_MAX_SUMMARY_CHARS",
    "LLM_CONTEXT_SUMMARY_GRAPH_CHAT_MODEL",
    "LLM_CONTEXT_SUMMARY_GRAPH_CHAT_TEMPERATURE",
    "LLM_CONTEXT_SUMMARY_GRAPH_CHAT_REASONING",
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_settings(**overrides) -> Settings:
    """
    Instantiate the real Settings against an environment where every compaction
    key is removed first, then the given overrides are applied.

    Removing the keys up front keeps the "default" tests honest even when the
    developer's shell (or a stray export) already defines one of them.
    """
    env = dict(os.environ)
    for key in _COMPACTION_ENV_KEYS:
        env.pop(key, None)
    env.update({key: str(value) for key, value in overrides.items()})
    with patch.dict(os.environ, env, clear=True):
        return Settings()


# ===========================================================================
# Defaults
# ===========================================================================


class TestChatCompactionSettingsDefaults:
    def test_chat_compaction_enabled__unset__defaults_to_true(self):
        assert _make_settings().chat_compaction_enabled is True

    def test_chat_compaction_trigger_messages__unset__defaults_to_30(self):
        assert _make_settings().chat_compaction_trigger_messages == 30

    def test_chat_compaction_trigger_chars__unset__defaults_to_24000(self):
        assert _make_settings().chat_compaction_trigger_chars == 24_000

    def test_chat_compaction_keep_tail_messages__unset__defaults_to_16(self):
        assert _make_settings().chat_compaction_keep_tail_messages == 16

    def test_chat_compaction_max_summary_chars__unset__defaults_to_2500(self):
        assert _make_settings().chat_compaction_max_summary_chars == 2_500

    def test_keep_tail__default__is_below_trigger_and_even(self):
        # Calibration invariant of §4: the verbatim tail must be smaller than
        # the trigger (otherwise there is nothing left to summarize) and even
        # (a whole number of human/ai turns).
        settings = _make_settings()
        assert (
            settings.chat_compaction_keep_tail_messages
            < settings.chat_compaction_trigger_messages
        )
        assert settings.chat_compaction_keep_tail_messages % 2 == 0

    def test_trigger_messages__default__not_above_only_talk_window(self):
        # "No gap" calibration of §4: the trigger must not exceed the only-talk
        # history window, otherwise the window would drop messages the summary
        # has not covered yet.
        settings = _make_settings()
        assert (
            settings.chat_compaction_trigger_messages
            <= settings.llm_only_talk_history_max_messages
        )


class TestContextSummaryGraphLlmSettingsDefaults:
    def test_model__unset__defaults_to_gemma4_12b(self):
        assert _make_settings().llm_context_summary_graph_chat_model == "gemma4:12b"

    def test_temperature__unset__defaults_to_0_2(self):
        assert _make_settings().llm_context_summary_graph_chat_temperature == pytest.approx(0.2)

    def test_reasoning__unset__defaults_to_none(self):
        # Three-state semantics: None means "inherit the global llm_reasoning".
        assert _make_settings().llm_context_summary_graph_chat_reasoning is None


# ===========================================================================
# Environment overrides
# ===========================================================================


class TestChatCompactionSettingsEnvOverride:
    def test_chat_compaction_enabled__env_false__is_disabled(self):
        settings = _make_settings(CHAT_COMPACTION_ENABLED="false")
        assert settings.chat_compaction_enabled is False

    def test_chat_compaction_trigger_messages__env_override__value_applied(self):
        assert _make_settings(
            CHAT_COMPACTION_TRIGGER_MESSAGES="6"
        ).chat_compaction_trigger_messages == 6

    def test_chat_compaction_trigger_chars__env_override__value_applied(self):
        assert _make_settings(
            CHAT_COMPACTION_TRIGGER_CHARS="1000"
        ).chat_compaction_trigger_chars == 1000

    def test_chat_compaction_keep_tail_messages__env_override__value_applied(self):
        assert _make_settings(
            CHAT_COMPACTION_KEEP_TAIL_MESSAGES="4"
        ).chat_compaction_keep_tail_messages == 4

    def test_chat_compaction_max_summary_chars__env_override__value_applied(self):
        assert _make_settings(
            CHAT_COMPACTION_MAX_SUMMARY_CHARS="800"
        ).chat_compaction_max_summary_chars == 800

    def test_context_summary_model__env_override__value_applied(self):
        assert _make_settings(
            LLM_CONTEXT_SUMMARY_GRAPH_CHAT_MODEL="qwen3:14b"
        ).llm_context_summary_graph_chat_model == "qwen3:14b"

    def test_context_summary_temperature__env_override__value_applied(self):
        assert _make_settings(
            LLM_CONTEXT_SUMMARY_GRAPH_CHAT_TEMPERATURE="0.7"
        ).llm_context_summary_graph_chat_temperature == pytest.approx(0.7)

    def test_context_summary_reasoning__env_true__is_true(self):
        assert (
            _make_settings(
                LLM_CONTEXT_SUMMARY_GRAPH_CHAT_REASONING="true"
            ).llm_context_summary_graph_chat_reasoning
            is True
        )

    def test_context_summary_reasoning__env_false__is_false(self):
        assert (
            _make_settings(
                LLM_CONTEXT_SUMMARY_GRAPH_CHAT_REASONING="false"
            ).llm_context_summary_graph_chat_reasoning
            is False
        )


# ===========================================================================
# Type coercion (env vars are always strings)
# ===========================================================================


class TestChatCompactionSettingsCoercion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("0", False),
        ],
    )
    def test_chat_compaction_enabled__string_value__coerced_to_bool(
        self, raw, expected
    ):
        settings = _make_settings(CHAT_COMPACTION_ENABLED=raw)
        assert settings.chat_compaction_enabled is expected

    @pytest.mark.parametrize(
        "key,attribute",
        [
            ("CHAT_COMPACTION_TRIGGER_MESSAGES", "chat_compaction_trigger_messages"),
            ("CHAT_COMPACTION_TRIGGER_CHARS", "chat_compaction_trigger_chars"),
            (
                "CHAT_COMPACTION_KEEP_TAIL_MESSAGES",
                "chat_compaction_keep_tail_messages",
            ),
            (
                "CHAT_COMPACTION_MAX_SUMMARY_CHARS",
                "chat_compaction_max_summary_chars",
            ),
        ],
    )
    def test_numeric_threshold__string_value__coerced_to_int(self, key, attribute):
        settings = _make_settings(**{key: "12"})
        value = getattr(settings, attribute)
        assert value == 12
        assert isinstance(value, int)

    def test_context_summary_temperature__string_value__coerced_to_float(self):
        value = _make_settings(
            LLM_CONTEXT_SUMMARY_GRAPH_CHAT_TEMPERATURE="0.5"
        ).llm_context_summary_graph_chat_temperature
        assert isinstance(value, float)
        assert value == pytest.approx(0.5)

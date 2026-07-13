"""
User settings (timezone) — LLM integration battery (§10.7). Requires a live Ollama.

These validate the whole chat chain against the real model:

  - B1 positive: "change/read my timezone" phrases route to ["user_settings"] and
    actually PERSIST the resolved IANA identifier. The assert is on the persisted
    state (the settings row), never on the wording of the answer — the LLM writes
    the sentence, Python writes the timezone.
  - B1 "que horas são?": with a timezone whose offset differs from the server's,
    the answer must carry the USER's local hour — the whole point of the feature.
  - B2 anti-false-positive: phrases that merely mention a city, a time, or another
    domain must NOT be classified as `user_settings` and must leave the user's
    settings untouched (no row written at all).

Acceptance: 100% per battery, with at most 2 flaky phrases per battery allowed to
be moved to an AMBIGUOUS_EXCLUDED list (documented), per the plan's process.
"""

import re

import pytest

from application.appservices.view_models import ChatRequest
from domain.services.clock import now_for_timezone
from infra.ioc import (
    get_user_app_service,
    get_user_settings_repository,
    get_user_settings_service,
)


pytestmark = pytest.mark.integration


SAO_PAULO = "America/Sao_Paulo"
LISBON = "Europe/Lisbon"

# The test host runs at UTC-3 and DEFAULT_TIMEZONE is America/Sao_Paulo, so a
# test that must PROVE the answer uses the *user's* timezone (and not the
# server's, nor the default) needs one whose offset differs from both: Lisbon is
# UTC+1 in July, i.e. 4h away from São Paulo. Asserting the hour with the
# timezones aligned would pass even if the feature did nothing.
DISCRIMINATING_TZ = LISBON

# Phrases dropped from a battery for being genuinely ambiguous (repo process:
# at most 2 per battery, each documented). None so far.
AMBIGUOUS_EXCLUDED: list[str] = []

# "14:32", "14h32", "2h05" — the hour/minute pair inside a free-form answer.
_TIME_PATTERN = re.compile(r"\b(\d{1,2})[:h](\d{2})\b")


@pytest.fixture
def settings_user_id(integration_user, integration_db_path):
    """The internal (UUID) id of the integration user — the settings row key."""
    user = get_user_app_service().get_by_external_id(
        external_id=integration_user.external_id
    )
    return user.id


def _persisted_timezone(user_id: str):
    """The persisted row, or None when the user never set a timezone.

    Read through the repository, not through ``UserSettingsService.get_timezone``:
    the service falls back to the default (America/Sao_Paulo), so a service-level
    assert would pass for a São Paulo set even if nothing had been written.
    """
    return get_user_settings_repository().get_by_user_id(user_id)


# ----------------------------------------------------------------------- #
# B1 — positive: set_timezone must route AND persist
# ----------------------------------------------------------------------- #
B1_SET = [
    ("Peruca, altere o meu timezone para São Paulo.", SAO_PAULO),
    ("Muda o fuso horário para Lisboa.", LISBON),
    ("Configura meu fuso para o horário de Brasília.", SAO_PAULO),
    ("Meu fuso está errado, troca para São Paulo.", SAO_PAULO),
    ("Define o horário de Portugal para mim.", LISBON),
]


@pytest.mark.parametrize("message,expected_timezone", B1_SET)
def test_b1_set_timezone__routes_and_persists(
    message, expected_timezone, llm_app_service, settings_user_id
):
    response = llm_app_service.chat(ChatRequest(external_user_id="1000", message=message))

    assert response.get("intents") == ["user_settings"], response
    assert response.get("output")

    settings = _persisted_timezone(settings_user_id)
    assert settings is not None, f"no settings row was written: {response}"
    assert settings.timezone == expected_timezone, response
    # And the service — the reader every graph goes through — agrees.
    assert (
        get_user_settings_service().get_timezone(settings_user_id) == expected_timezone
    )


# ----------------------------------------------------------------------- #
# B1 — positive: get_timezone reads the configured value, writes nothing
# ----------------------------------------------------------------------- #
def test_b1_get_timezone__routes_and_reports_configured_value(
    llm_app_service, settings_user_id
):
    get_user_settings_service().set_timezone(settings_user_id, LISBON)

    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message="Qual é o fuso horário configurado?")
    )

    assert response.get("intents") == ["user_settings"], response
    assert LISBON in (response.get("output") or ""), response
    # A read never writes: the configured timezone is untouched.
    assert _persisted_timezone(settings_user_id).timezone == LISBON


# ----------------------------------------------------------------------- #
# B1 — "que horas são?" answers in the USER's timezone (the feature itself)
# ----------------------------------------------------------------------- #
def test_b1_what_time_is_it__answers_in_the_users_timezone(
    llm_app_service, settings_user_id
):
    """
    The timezone is set through the service (deterministic setup — the chat write
    path is already covered by B1_SET); what is under test here is that the ANSWER
    uses it.

    No minute-level flakiness by construction: the local hour is captured before
    and after the chat call and the answer's hour only has to be one of the two.
    Proving the *timezone* (4h away from the server's) is the point, not the minute.
    """
    get_user_settings_service().set_timezone(settings_user_id, DISCRIMINATING_TZ)

    before = now_for_timezone(DISCRIMINATING_TZ)
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message="Que horas são?")
    )
    after = now_for_timezone(DISCRIMINATING_TZ)

    output = response.get("output") or ""
    hours = {int(hour) for hour, _ in _TIME_PATTERN.findall(output)}
    assert hours, f"no clock time in the answer: {output!r}"
    assert hours & {before.hour, after.hour}, (
        f"answer does not carry the user's local hour "
        f"({before.hour}h/{after.hour}h in {DISCRIMINATING_TZ}): {output!r}"
    )


# ----------------------------------------------------------------------- #
# B2 — anti-false-positive: must NOT be user_settings, must not write settings
# ----------------------------------------------------------------------- #
B2_ONLY_TALKING = [
    # Asking the time is conversation, not configuration.
    "Que horas são?",
    # The most critical guard: a city mentioned with no command at all.
    "Vou viajar para Lisboa semana que vem.",
]


@pytest.mark.parametrize("message", B2_ONLY_TALKING)
def test_b2_anti_false_positive__routes_to_only_talking(
    message, llm_app_service, settings_user_id
):
    response = llm_app_service.chat(ChatRequest(external_user_id="1000", message=message))

    intents = response.get("intents") or []
    assert intents == ["only_talking"], response
    assert "user_settings" not in intents, response
    assert _persisted_timezone(settings_user_id) is None, (
        "an anti-false-positive phrase wrote the user's settings"
    )


def test_b2_anti_false_positive__music_is_not_a_setting(
    llm_app_service, settings_user_id, music_assistant_available
):
    """"Põe uma música..." — an imperative that is not a configuration."""
    response = llm_app_service.chat(
        ChatRequest(
            external_user_id="1000", message="Põe uma música da década de 80."
        )
    )

    intents = response.get("intents") or []
    assert intents == ["music"], response
    assert "user_settings" not in intents, response
    assert _persisted_timezone(settings_user_id) is None


def test_b2_anti_false_positive__sensors_is_not_a_setting(
    llm_app_service, settings_user_id, home_assistant_available
):
    """A temperature question is a sensor reading, not a setting."""
    response = llm_app_service.chat(
        ChatRequest(external_user_id="1000", message="Qual a temperatura lá fora?")
    )

    intents = response.get("intents") or []
    assert intents == ["smart_home_sensors"], response
    assert "user_settings" not in intents, response
    assert _persisted_timezone(settings_user_id) is None

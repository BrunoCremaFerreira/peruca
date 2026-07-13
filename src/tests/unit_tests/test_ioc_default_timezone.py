"""
DEFAULT_TIMEZONE must fail at COMPOSITION, never at request time — TZ-003.

`UserSettingsService.get_timezone()` returns the injected default RAW (no
revalidation) for every user without a row in `user_settings` — which is every user
until they set one. So a typo in the operator's env (`America/Sao_Paolo`) does not
degrade anything gracefully: the value reaches `clock`, which correctly raises
`ValidationError`, and EVERY chat turn of EVERY default user dies at request time,
with the cause buried in a graph stack trace.

The default timezone is policy injected by the composition root, so it must be
validated where it is composed: building the service with an invalid IANA identifier
is a configuration error and must blow up loudly, once, at boot.

Contract fixed by these tests:

    UserSettingsService(user_settings_repository, default_timezone)
        raises domain ValidationError when `default_timezone` is not a valid IANA
        identifier (empty included) — the same authority as `clock`, no new concept.

    infra.ioc.get_user_settings_service()
        therefore raises ValidationError when DEFAULT_TIMEZONE is misconfigured, and
        composes normally when it is valid.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from domain.exceptions import ValidationError
from domain.services.user_settings_service import UserSettingsService
from infra.ioc import get_user_settings_service


_VALID_ENV = {
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://ollama-host:11434",
    "LLM_PROVIDER_API_KEY": "",
}


def _make_repo():
    repo = MagicMock()
    repo.get_by_user_id.return_value = None
    return repo


class TestUserSettingsServiceValidatesItsDefault:
    def test_invalid_default__raises_at_construction(self):
        with pytest.raises(ValidationError):
            UserSettingsService(
                user_settings_repository=_make_repo(),
                default_timezone="America/Sao_Paolo",  # the classic typo
            )

    def test_empty_default__raises_at_construction(self):
        with pytest.raises(ValidationError):
            UserSettingsService(
                user_settings_repository=_make_repo(), default_timezone=""
            )

    def test_valid_default__constructs_and_is_served(self):
        service = UserSettingsService(
            user_settings_repository=_make_repo(), default_timezone="Europe/Lisbon"
        )
        assert service.get_timezone("user-1") == "Europe/Lisbon"

    def test_invalid_default__never_reaches_a_request(self):
        # The point of failing at construction: no user can ever be handed a
        # broken timezone by get_timezone().
        with pytest.raises(ValidationError):
            UserSettingsService(
                user_settings_repository=_make_repo(), default_timezone="Mars/Olympus"
            )


class TestIocComposition:
    def test_misconfigured_env__factory_fails_loudly(self):
        with patch.dict(
            os.environ, {**_VALID_ENV, "DEFAULT_TIMEZONE": "America/Sao_Paolo"}
        ):
            with pytest.raises(ValidationError):
                get_user_settings_service()

    def test_valid_env__factory_composes(self):
        with patch.dict(
            os.environ, {**_VALID_ENV, "DEFAULT_TIMEZONE": "America/Manaus"}
        ):
            service = get_user_settings_service()
            assert service.default_timezone == "America/Manaus"

    def test_default_env__composes(self):
        # The shipped default (America/Sao_Paulo) must obviously pass its own guard.
        with patch.dict(os.environ, _VALID_ENV):
            os.environ.pop("DEFAULT_TIMEZONE", None)
            service = get_user_settings_service()
            assert service.default_timezone == "America/Sao_Paulo"

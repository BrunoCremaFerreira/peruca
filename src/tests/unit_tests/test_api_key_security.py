"""
require_api_key unit tests (TDD).

Migration mode: with PERUCA_API_KEY unset the dependency is a no-op (the API
stays open). Once the key is set, a missing/wrong key raises 401 and the exact
key passes. Comparison is constant-time and must not crash on non-ASCII input.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from infra.security import require_api_key


class TestRequireApiKey:
    def test_key_not_configured__is_noop(self):
        with patch.dict(os.environ, {"PERUCA_API_KEY": ""}, clear=False):
            assert require_api_key(None) is None
            assert require_api_key("anything") is None

    def test_key_configured_missing_header__raises_401(self):
        with patch.dict(os.environ, {"PERUCA_API_KEY": "s3cr3t"}, clear=False):
            with pytest.raises(HTTPException) as exc:
                require_api_key(None)
            assert exc.value.status_code == 401

    def test_key_configured_wrong__raises_401(self):
        with patch.dict(os.environ, {"PERUCA_API_KEY": "s3cr3t"}, clear=False):
            with pytest.raises(HTTPException) as exc:
                require_api_key("wrong")
            assert exc.value.status_code == 401

    def test_key_configured_correct__passes(self):
        with patch.dict(os.environ, {"PERUCA_API_KEY": "s3cr3t"}, clear=False):
            assert require_api_key("s3cr3t") is None

    def test_unicode_provided_does_not_crash(self):
        with patch.dict(os.environ, {"PERUCA_API_KEY": "s3cr3t"}, clear=False):
            with pytest.raises(HTTPException):
                require_api_key("çãÿ★")

"""
Router-level API-key enforcement (TDD).

/health is public. Every other route requires X-API-Key when PERUCA_API_KEY is
set; with it unset the API stays open (migration mode). Uses TestClient +
dependency_overrides so no real app service is exercised — auth runs before the
handler.
"""

import os
import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import app
from application.appservices.view_models import VehicleResponse
from infra.ioc import get_vehicle_app_service


def _client():
    return TestClient(app)


def _override_vehicle_service():
    svc = MagicMock()
    svc.get_by_id.return_value = VehicleResponse(id="v", name="Mitsubishi Outlander")
    app.dependency_overrides[get_vehicle_app_service] = lambda: svc
    return svc


def _clear_overrides():
    app.dependency_overrides.clear()


class TestPublicHealth:
    def test_health_is_public_even_with_key(self):
        with _patch_key("s3cr3t"):
            assert _client().get("/health").status_code == 200


class TestProtectedRoutes:
    def test_missing_key__401(self):
        _override_vehicle_service()
        try:
            with _patch_key("s3cr3t"):
                resp = _client().get(f"/vehicle/{uuid.uuid4()}")
            assert resp.status_code == 401
        finally:
            _clear_overrides()

    def test_wrong_key__401(self):
        _override_vehicle_service()
        try:
            with _patch_key("s3cr3t"):
                resp = _client().get(
                    f"/vehicle/{uuid.uuid4()}", headers={"X-API-Key": "nope"}
                )
            assert resp.status_code == 401
        finally:
            _clear_overrides()

    def test_correct_key__200(self):
        _override_vehicle_service()
        try:
            with _patch_key("s3cr3t"):
                resp = _client().get(
                    f"/vehicle/{uuid.uuid4()}", headers={"X-API-Key": "s3cr3t"}
                )
            assert resp.status_code == 200
        finally:
            _clear_overrides()

    def test_migration_mode_open__200_without_key(self):
        _override_vehicle_service()
        try:
            with _patch_key(""):
                resp = _client().get(f"/vehicle/{uuid.uuid4()}")
            assert resp.status_code == 200
        finally:
            _clear_overrides()


class _patch_key:
    """Context manager setting PERUCA_API_KEY for the duration of a request."""

    def __init__(self, value):
        self.value = value
        self._old = None

    def __enter__(self):
        self._old = os.environ.get("PERUCA_API_KEY")
        os.environ["PERUCA_API_KEY"] = self.value
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("PERUCA_API_KEY", None)
        else:
            os.environ["PERUCA_API_KEY"] = self._old

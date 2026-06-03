"""
Health endpoint unit tests (TDD - RED phase)

Tests the GET /health liveness probe endpoint that will be added to routes.py:

    @router.get("/health")
    async def health():
        return {"status": "ok"}

The endpoint has no dependencies (no IoC, no DB, no LLM).

These tests are expected to FAIL (404 Not Found) until the route is implemented
in routes.py.
"""

from fastapi.testclient import TestClient
from app import app


client = TestClient(app)


class TestHealthRoute:
    def test_health__get__returns_200(self):
        # Act
        response = client.get("/health")
        # Assert
        assert response.status_code == 200

    def test_health__get__returns_status_ok(self):
        # Act
        response = client.get("/health")
        # Assert
        assert response.json() == {"status": "ok"}

"""
DELETE /user/{id}/chat-history route Unit Tests (TDD - RED phase)

New feature (plan §2.2 / §4.2):
    A REST-only endpoint that resets a user's conversation history:

        @router.delete("/user/{id}/chat-history", tags=["User Chat History"])
        def user_chat_history_reset(
            id: str,
            llm_app_service: LlmAppService = Depends(get_llm_app_service),
        ) -> None:
            llm_app_service.reset_context(user_id=id)

    - No user-existence check, idempotent, implicit 200.
    - Sits under the authenticated router (X-API-Key). Here PERUCA_API_KEY is
      unset (migration mode = open), so TestClient calls need no header — same
      as the other unit route tests.

TestClient + dependency_overrides so no real app service is exercised.

Expected to FAIL until routes.py gains the route:
    404 Not Found (route does not exist yet), so reset_context is never called.
"""

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import app
from infra.ioc import get_llm_app_service


def _client():
    return TestClient(app)


def _override_llm_service():
    svc = MagicMock()
    svc.reset_context.return_value = None
    app.dependency_overrides[get_llm_app_service] = lambda: svc
    return svc


def _clear_overrides():
    app.dependency_overrides.clear()


class TestDeleteChatHistory:
    def test_delete_chat_history__calls_reset_context_with_path_id(self):
        # Arrange
        user_id = str(uuid.uuid4())
        svc = _override_llm_service()
        try:
            # Act
            _client().delete(f"/user/{user_id}/chat-history")
            # Assert — the path id is forwarded as the reset scope.
            svc.reset_context.assert_called_once_with(user_id=user_id)
        finally:
            _clear_overrides()

    def test_delete_chat_history__returns_200(self):
        # Arrange
        user_id = str(uuid.uuid4())
        _override_llm_service()
        try:
            # Act
            resp = _client().delete(f"/user/{user_id}/chat-history")
            # Assert — implicit 200 (project convention for "clear" routes).
            assert resp.status_code == 200
        finally:
            _clear_overrides()

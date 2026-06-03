"""
LlmAppService enrichment Unit Tests (TDD - RED phase)

LlmAppService gains a new dependency `user_memory_service` and, in chat(),
loads the user's memories synchronously and injects them into the
GraphInvokeRequest as `memories=[m.content for ...]` BEFORE invoking the
main graph. Extraction is NOT done here (moved to background MemoryAppService).

New constructor contract:
    LlmAppService(main_graph, context_repository, user_repository,
                  user_memory_service)

Behaviours covered:
  - memories loaded and passed to GraphInvokeRequest (captured via
    main_graph.invoke.call_args)
  - non-existent user still raises NofFoundValidationError (preserved)

Expected to FAIL with TypeError (extra ctor arg) / AttributeError until the
service is updated.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User, UserMemory
from domain.exceptions import NofFoundValidationError


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="resumo")


def _make_service(user=None, memories=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = {"output": "ok", "intent": ["only_talking"]}

    context_repository = MagicMock()

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = memories or []

    service = LlmAppService(
        main_graph,
        context_repository,
        user_repository,
        user_memory_service,
    )
    return service, main_graph, user_memory_service


# ===========================================================================
# TestLlmAppServiceEnrichment
# ===========================================================================


class TestLlmAppServiceEnrichment:
    def test_chat__loads_memories_and_passes_to_graph_request(self):
        # Arrange
        user = _sample_user()
        memories = [UserMemory(id=str(uuid.uuid4()), user_id=user.id, content="X")]
        service, main_graph, user_memory_service = _make_service(
            user=user, memories=memories
        )
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )
        # Act
        service.chat(request)
        # Assert
        user_memory_service.get_all_by_user.assert_called_once_with(user.id)
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.memories == ["X"]

    def test_chat__no_memories__passes_empty_list(self):
        # Arrange
        user = _sample_user()
        service, main_graph, _ = _make_service(user=user, memories=[])
        request = ChatRequest(
            message="oi", external_user_id=user.external_id, chat_id="c1"
        )
        # Act
        service.chat(request)
        # Assert
        graph_request = main_graph.invoke.call_args[1]["invoke_request"]
        assert graph_request.memories == []


# ===========================================================================
# TestLlmAppServiceErrors
# ===========================================================================


class TestLlmAppServiceErrors:
    def test_chat__unknown_user__raises_not_found(self):
        # Arrange
        service, main_graph, _ = _make_service(user=None)
        request = ChatRequest(
            message="oi", external_user_id=str(uuid.uuid4()), chat_id="c1"
        )
        # Act / Assert
        with pytest.raises(NofFoundValidationError):
            service.chat(request)
        main_graph.invoke.assert_not_called()

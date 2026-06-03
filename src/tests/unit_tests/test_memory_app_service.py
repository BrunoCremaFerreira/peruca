"""
MemoryAppService Unit Tests (TDD - RED phase)

MemoryAppService.learn_from_message(external_user_id, message, assistant_output)
is SYNCHRONOUS (it has no notion of background tasks) and its entire body is
wrapped in try/except so failures NEVER propagate.

Constructor contract:
    MemoryAppService(memory_graph, user_repository,
                     user_memory_repository_factory)
where user_memory_repository_factory is a callable returning a repository with
its OWN connection (thread-safety for the background threadpool).

Flow inside learn_from_message:
    repo = factory()
    try:
        user = user_repository.get_by_external_id(external_user_id)
        if not user: return
        existing = UserMemoryService(repo).get_all_by_user(user.id)
        extracted = memory_graph.invoke(GraphInvokeRequest(message, user, existing))
        for fact in extracted["memories"]:
            UserMemoryService(repo).add(UserMemoryAdd(user.id, fact))
    finally:
        repo.close()

Test strategy:
  - Persistence/dedup assertions PATCH
    `application.appservices.memory_app_service.UserMemoryService` with a mock
    service so we can assert .add was called per fact deterministically, without
    depending on the service's internal dedup logic.
  - The repo.close() / error-swallowing tests use the real factory mock repo.

Expected to FAIL with ImportError until the app service exists.
"""

import uuid
from unittest.mock import MagicMock, patch

from application.appservices.memory_app_service import MemoryAppService
from domain.entities import User


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id="ext-1", name="Alice", summary="")


def _make_service(user=None, extracted=None, graph_raises=False):
    repo = MagicMock()
    repo.get_all_by_user_id.return_value = []
    factory = MagicMock(return_value=repo)

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    memory_graph = MagicMock()
    if graph_raises:
        memory_graph.invoke.side_effect = RuntimeError("boom")
    else:
        memory_graph.invoke.return_value = {"memories": extracted or []}

    service = MemoryAppService(memory_graph, user_repository, factory)
    return service, memory_graph, user_repository, factory, repo


# ===========================================================================
# TestMemoryAppServicePersistence
# ===========================================================================


class TestMemoryAppServicePersistence:
    def test_learn_from_message__persists_each_extracted_fact(self):
        """Patches UserMemoryService to assert .add is called once per fact."""
        # Arrange
        user = _sample_user()
        service, _, _, _, _ = _make_service(
            user=user, extracted=["fato A", "fato B"]
        )
        with patch(
            "application.appservices.memory_app_service.UserMemoryService"
        ) as svc_cls:
            inner = svc_cls.return_value
            inner.get_all_by_user.return_value = []
            # Act
            service.learn_from_message("ext-1", "minha mensagem", "resposta")
            # Assert
            assert inner.add.call_count == 2


# ===========================================================================
# TestMemoryAppServiceDedup
# ===========================================================================


class TestMemoryAppServiceDedup:
    def test_learn_from_message__existing_fact_not_re_added(self):
        """
        With the REAL UserMemoryService (dedup via repo.get_all_by_user_id),
        configure the repo to already contain "fato A" so only "fato B" persists.
        """
        # Arrange
        from domain.entities import UserMemory

        user = _sample_user()
        service, _, _, _, repo = _make_service(
            user=user, extracted=["fato A", "fato B"]
        )
        repo.get_all_by_user_id.return_value = [
            UserMemory(id=str(uuid.uuid4()), user_id=user.id, content="fato A")
        ]
        # Act
        service.learn_from_message("ext-1", "msg", "resp")
        # Assert (only "fato B" is new -> repo.add called once)
        assert repo.add.call_count == 1


# ===========================================================================
# TestMemoryAppServiceResilience
# ===========================================================================


class TestMemoryAppServiceResilience:
    def test_learn_from_message__graph_error_does_not_propagate(self):
        # Arrange
        user = _sample_user()
        service, _, _, _, _ = _make_service(user=user, graph_raises=True)
        # Act / Assert (must not raise)
        service.learn_from_message("ext-1", "msg", "resp")

    def test_learn_from_message__unknown_user__returns_without_error(self):
        # Arrange
        service, memory_graph, _, _, _ = _make_service(user=None)
        # Act / Assert (must not raise; graph never invoked)
        service.learn_from_message("ext-unknown", "msg", "resp")
        memory_graph.invoke.assert_not_called()

    def test_learn_from_message__closes_repo_in_finally_even_on_error(self):
        # Arrange
        user = _sample_user()
        service, _, _, _, repo = _make_service(user=user, graph_raises=True)
        # Act
        service.learn_from_message("ext-1", "msg", "resp")
        # Assert
        repo.close.assert_called()

    def test_learn_from_message__closes_repo_on_success(self):
        # Arrange
        user = _sample_user()
        service, _, _, _, repo = _make_service(user=user, extracted=["fato A"])
        # Act
        service.learn_from_message("ext-1", "msg", "resp")
        # Assert
        repo.close.assert_called()

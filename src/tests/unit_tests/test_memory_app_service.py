"""
MemoryAppService Unit Tests

MemoryAppService.learn_from_message(external_user_id, message, assistant_output)
is SYNCHRONOUS (it has no notion of background tasks) and its entire body is
wrapped in try/except so failures NEVER propagate.

Constructor contract:
    MemoryAppService(memory_graph, user_repository,
                     user_memory_repository_factory)
where user_memory_repository_factory is a callable returning a shared cached
repository. The caller must NOT close the repo — lifecycle is managed by the IoC
container.

Test strategy:
  - Persistence/dedup assertions PATCH
    `application.appservices.memory_app_service.UserMemoryService` with a mock
    service so we can assert .add was called per fact deterministically, without
    depending on the service's internal dedup logic.
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


# ===========================================================================
# TestMemoryAppServiceDataUriSanitization (F1 — cameras review plan §3.2)
# ===========================================================================


class TestMemoryAppServiceDataUriSanitization:
    def test_learn_from_message__assistant_output_with_data_uri__memory_graph_never_receives_uri(
        self,
    ):
        """
        F1: routes.py hands the RAW chat output to learn_from_message. When it
        carries a camera snapshot data URI ("data:image/..." line), that
        base64 blob must NEVER reach the MemoryGraph LLM — the text handed to
        memory_graph.invoke must contain no 'data:image/' fragment (the URI
        line is replaced by the sanitizer placeholder before the graph call).
        """
        # Arrange
        import base64

        user = _sample_user()
        service, memory_graph, _, _, _ = _make_service(user=user, extracted=[])
        encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfake_png").decode()
        uri = f"data:image/png;base64,{encoded}"
        assistant_output = f"{uri}\nCamera Sala: gravando"
        # Act
        service.learn_from_message(
            "ext-1", "mostra a câmera da sala", assistant_output
        )
        # Assert — nothing that reaches the MemoryGraph may carry the URI.
        assert memory_graph.invoke.called, (
            "Expected the MemoryGraph to be invoked for a valid user"
        )
        everything_sent = str(memory_graph.invoke.call_args)
        assert "data:image/" not in everything_sent, (
            f"Camera data URI leaked into the MemoryGraph input: "
            f"{everything_sent[:200]!r}"
        )

    def test_learn_from_message__unknown_user__returns_without_error(self):
        # Arrange
        service, memory_graph, _, _, _ = _make_service(user=None)
        # Act / Assert (must not raise; graph never invoked)
        service.learn_from_message("ext-unknown", "msg", "resp")
        memory_graph.invoke.assert_not_called()

    def test_learn_from_message__does_not_close_shared_repo_on_error(self):
        # Arrange — repo is a cached singleton; caller must never close it
        user = _sample_user()
        service, _, _, _, repo = _make_service(user=user, graph_raises=True)
        # Act
        service.learn_from_message("ext-1", "msg", "resp")
        # Assert
        repo.close.assert_not_called()

    def test_learn_from_message__does_not_close_shared_repo_on_success(self):
        # Arrange — repo is a cached singleton; caller must never close it
        user = _sample_user()
        service, _, _, _, repo = _make_service(user=user, extracted=["fato A"])
        # Act
        service.learn_from_message("ext-1", "msg", "resp")
        # Assert
        repo.close.assert_not_called()

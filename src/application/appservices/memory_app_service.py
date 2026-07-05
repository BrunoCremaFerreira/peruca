import logging
from typing import Callable

from application.graphs.memory_graph import MemoryGraph
from domain.commands import UserMemoryAdd
from domain.entities import GraphInvokeRequest
from domain.interfaces.data_repository import UserMemoryRepository, UserRepository
from domain.services.user_memory_service import UserMemoryService


logger = logging.getLogger(__name__)


class MemoryAppService:
    """
    Memory Application Service (background extraction + persistence).

    Synchronous, with no notion of background tasks. The entire body of
    learn_from_message is wrapped in try/except so failures never propagate
    to the caller (it runs in a background threadpool).
    """

    def __init__(
        self,
        memory_graph: MemoryGraph,
        user_repository: UserRepository,
        user_memory_repository_factory: Callable[[], UserMemoryRepository],
    ) -> None:
        self.memory_graph = memory_graph
        self.user_repository = user_repository
        self.user_memory_repository_factory = user_memory_repository_factory

    def learn_from_message(
        self, external_user_id: str, message: str, assistant_output: str
    ) -> None:
        repo = None
        try:
            repo = self.user_memory_repository_factory()

            user = self.user_repository.get_by_external_id(external_id=external_user_id)
            if not user:
                return

            existing = repo.get_all_by_user_id(user.id)
            existing_contents = [memory.content for memory in existing]

            request = GraphInvokeRequest(
                message=message, user=user, memories=existing_contents
            )

            result = self.memory_graph.invoke(request)
            facts = result.get("memories", [])

            service = UserMemoryService(user_memory_repository=repo)
            for fact in facts:
                service.add(UserMemoryAdd(user_id=user.id, content=fact))
        except Exception as e:
            logger.error("learn_from_message failed: %s", e, exc_info=True)

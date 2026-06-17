import asyncio
from infra import async_runner
from typing import Callable, Optional

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from application.appservices.view_models import ChatRequest
from application.graphs.main_graph import MainGraph
from domain.entities import GraphInvokeRequest, User
from domain.exceptions import EmptyParamValidationError, NofFoundValidationError
from domain.interfaces.data_repository import ContextRepository, UserRepository
from domain.services.user_memory_service import UserMemoryService
from infra.utils import is_null_or_whitespace


_MUSIC_PROBE_TIMEOUT = 2.0


class LlmAppService:
    """
    LLM Application Service
    """

    def __init__(
        self,
        main_graph: MainGraph,
        context_repository: Optional[ContextRepository],
        user_repository: UserRepository,
        user_memory_service: UserMemoryService,
        music_service=None,
        get_session_history: Optional[
            Callable[[str], BaseChatMessageHistory]
        ] = None,
    ) -> None:
        self.main_graph = main_graph
        self.context_repository = context_repository
        self.user_repository = user_repository
        self.user_memory_service = user_memory_service
        self.music_service = music_service
        self.get_session_history = get_session_history

    # ===============================================
    # Public Methods
    # ===============================================

    def chat(self, chat_request: ChatRequest) -> str:
        print(f"[LlmAppService.chat]: Request: {{ {chat_request} }}")

        if is_null_or_whitespace(chat_request.external_user_id):
            raise EmptyParamValidationError(param_name="external_user_id")

        user = self.user_repository.get_by_external_id(
            external_id=chat_request.external_user_id
        )

        if not user:
            raise NofFoundValidationError(
                entity_name="user",
                key_name="external_id",
                value=chat_request.external_user_id,
            )

        memories = self.user_memory_service.get_all_by_user(user.id)
        memory_contents = [memory.content for memory in memories]

        context_hints: dict = {}
        if self.music_service is not None:
            try:
                players = async_runner.run(
                    asyncio.wait_for(
                        self.music_service.get_players(),
                        timeout=_MUSIC_PROBE_TIMEOUT,
                    )
                )
                music_is_playing = any(p.state == "playing" for p in players)
            except Exception:
                music_is_playing = False
            context_hints = {"music_is_playing": music_is_playing}

        invoke_request = GraphInvokeRequest(
            message=chat_request.message,
            user=user,
            memories=memory_contents,
            context_hints=context_hints,
        )
        result = self.main_graph.invoke(invoke_request=invoke_request)
        output = result.get("output")
        intents = result.get("intent")

        self._persist_turn(user=user, message=chat_request.message, output=output)

        print(f"[LlmAppService.chat]: Response: '{result}'")
        return {"intents": intents, "output": output}

    # ===============================================
    # Private Methods
    # ===============================================

    def _persist_turn(self, user: User, message: str, output: Optional[str]) -> None:
        if self.get_session_history is None:
            return

        if is_null_or_whitespace(output):
            return

        try:
            history = self.get_session_history(user.id)
            history.add_messages(
                [HumanMessage(content=message), AIMessage(content=output)]
            )
        except Exception as error:
            print(f"[LlmAppService.chat]: Failed to persist turn: {error}")

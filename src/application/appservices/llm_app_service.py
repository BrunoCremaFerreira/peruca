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
        shopping_list_service=None,
        disambiguation_service=None,
    ) -> None:
        self.main_graph = main_graph
        self.context_repository = context_repository
        self.user_repository = user_repository
        self.user_memory_service = user_memory_service
        self.music_service = music_service
        self.get_session_history = get_session_history
        self.shopping_list_service = shopping_list_service
        self.disambiguation_service = disambiguation_service

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

        # A pending disambiguation short-circuits normal routing: the user's
        # reply ("a primeira" / "carne de panela" / "cancelar") is resolved
        # deterministically without invoking the MainGraph (no extra LLM cost).
        if self.disambiguation_service is not None:
            pending = async_runner.run(
                self.disambiguation_service.get_pending(user.id)
            )
            if pending is not None:
                consumed = self._consume_disambiguation(
                    user, pending, chat_request.message
                )
                if consumed is not None:
                    return consumed

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

    _OPERATION_LABELS = {
        "delete": "Removido",
        "check": "Marcado como comprado",
        "uncheck": "Desmarcado",
    }

    def _consume_disambiguation(self, user: User, pending, message: str):
        """
        Resolve a follow-up reply against a pending disambiguation.

        Returns the final chat response dict for "match"/"cancel", or None for
        "none" (the caller then falls through to the MainGraph with the original
        message).
        """
        result = self.disambiguation_service.resolve_choice(
            message, pending.candidates
        )

        if result.kind == "cancel":
            async_runner.run(self.disambiguation_service.clear_pending(user.id))
            output = "Ok, cancelei."
            self._persist_turn(user=user, message=message, output=output)
            return {"intents": ["shopping_list"], "output": output}

        if result.kind == "match":
            candidate = result.candidate
            self._apply_operation(pending.operation, candidate.id)
            async_runner.run(self.disambiguation_service.clear_pending(user.id))
            label = self._OPERATION_LABELS.get(pending.operation, "Feito")
            output = f"{label}: {candidate.name}"
            self._persist_turn(user=user, message=message, output=output)
            return {"intents": ["shopping_list"], "output": output}

        # kind == "none": the user ignored the question — drop the pending state
        # and let the original message route normally.
        async_runner.run(self.disambiguation_service.clear_pending(user.id))
        return None

    def _apply_operation(self, operation: str, item_id: str) -> None:
        operations = {
            "delete": self.shopping_list_service.delete,
            "check": self.shopping_list_service.check,
            "uncheck": self.shopping_list_service.uncheck,
        }
        apply = operations.get(operation)
        if apply is not None:
            apply(item_id)

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

"""
routes.chat background compaction scheduling Unit Tests (TDD - RED phase, Fase E/F7).

Target contract (plan §3.4, §6.5): the /llm/chat route gains a second injected
dependency and schedules a SECOND background task, after the memory one:

    @router.post("/llm/chat", tags=["LLM"])
    def chat(
        request: ChatRequest,
        background_tasks: BackgroundTasks,
        llm_app_service: LlmAppService = Depends(get_llm_app_service),
        memory_app_service: MemoryAppService = Depends(get_memory_app_service),
        context_compaction_app_service: ContextCompactionAppService = Depends(
            get_context_compaction_app_service
        ),
    ) -> ChatResponse:
        result = llm_app_service.chat(request)
        output = ...
        background_tasks.add_task(memory_app_service.learn_from_message, ...)
        background_tasks.add_task(
            context_compaction_app_service.compact_if_needed,
            request.external_user_id,
        )
        return ChatResponse(...)

Order matters (§6.5): durable-memory extraction runs FIRST — it reads the turn
that was just persisted, while compaction may rewrite the head of the history.

These are unit tests: `chat` is called directly with mocks / a real
BackgroundTasks. Scheduling is deliberately NOT exercised through TestClient
(that would re-test FastAPI itself — plan §7, "não testar").

Expected to FAIL until routes.chat accepts context_compaction_app_service:
    TypeError: chat() got an unexpected keyword argument
    'context_compaction_app_service'.
"""

from unittest.mock import MagicMock

from fastapi import BackgroundTasks

from application.appservices.view_models import ChatRequest
import routes


# ===========================================================================
# Helpers
# ===========================================================================


def _make_args(output="resposta", background_tasks=None):
    llm_app_service = MagicMock()
    llm_app_service.chat.return_value = {
        "output": output,
        "intents": ["only_talking"],
    }
    request = ChatRequest(
        message="me lembra do que a gente combinou?",
        external_user_id="ext-123",
        chat_id="chat-1",
    )
    return {
        "request": request,
        "background_tasks": background_tasks or MagicMock(),
        "llm_app_service": llm_app_service,
        "memory_app_service": MagicMock(),
        "context_compaction_app_service": MagicMock(),
    }


# ===========================================================================
# TestChatSchedulesCompaction
# ===========================================================================


class TestChatSchedulesCompaction:
    def test_chat__schedules_two_background_tasks(self):
        # Arrange
        args = _make_args()
        # Act
        routes.chat(**args)
        # Assert
        assert args["background_tasks"].add_task.call_count == 2

    def test_chat__schedules_compact_if_needed_with_external_user_id(self):
        # Arrange
        args = _make_args()
        compaction = args["context_compaction_app_service"]
        # Act
        routes.chat(**args)
        # Assert — the compaction task takes the EXTERNAL id (it resolves the
        # user itself, like learn_from_message).
        calls = args["background_tasks"].add_task.call_args_list
        scheduled = [
            list(call.args) + list(call.kwargs.values()) for call in calls
        ]
        assert any(
            compaction.compact_if_needed in params and "ext-123" in params
            for params in scheduled
        )

    def test_chat__compaction_task_is_not_invoked_synchronously(self):
        # Arrange — it must be SCHEDULED, never awaited in the request path
        # (an LLM call in the response path would violate req. 3 of the plan).
        args = _make_args()
        # Act
        routes.chat(**args)
        # Assert
        args["context_compaction_app_service"].compact_if_needed.assert_not_called()


# ===========================================================================
# TestChatBackgroundTaskOrder (§6.5)
# ===========================================================================


class TestChatBackgroundTaskOrder:
    def test_chat__memory_task_is_scheduled_before_compaction_task(self):
        # Arrange
        args = _make_args()
        memory = args["memory_app_service"]
        compaction = args["context_compaction_app_service"]
        # Act
        routes.chat(**args)
        # Assert
        calls = args["background_tasks"].add_task.call_args_list
        assert calls[0].args[0] is memory.learn_from_message
        assert calls[1].args[0] is compaction.compact_if_needed

    def test_chat__real_background_tasks__holds_both_callables_in_order(self):
        # Arrange — a real BackgroundTasks records what FastAPI would run.
        background_tasks = BackgroundTasks()
        args = _make_args(background_tasks=background_tasks)
        memory = args["memory_app_service"]
        compaction = args["context_compaction_app_service"]
        # Act
        routes.chat(**args)
        # Assert
        assert len(background_tasks.tasks) == 2
        assert background_tasks.tasks[0].func is memory.learn_from_message
        assert background_tasks.tasks[1].func is compaction.compact_if_needed

    def test_chat__real_background_tasks__compaction_task_carries_external_user_id(
        self,
    ):
        # Arrange
        background_tasks = BackgroundTasks()
        args = _make_args(background_tasks=background_tasks)
        # Act
        routes.chat(**args)
        # Assert
        compaction_task = background_tasks.tasks[1]
        params = list(compaction_task.args) + list(compaction_task.kwargs.values())
        assert params == ["ext-123"]


# ===========================================================================
# TestChatResponseContractUnchanged
# ===========================================================================


class TestChatResponseContractUnchanged:
    """The second background task must not touch the response contract."""

    def test_chat__response_field_is_still_the_output_string(self):
        # Arrange
        args = _make_args(output="olá mundo")
        # Act
        result = routes.chat(**args)
        # Assert
        assert result.response == "olá mundo"
        assert isinstance(result.response, str)

    def test_chat__still_propagates_identifiers(self):
        # Arrange
        args = _make_args()
        # Act
        result = routes.chat(**args)
        # Assert
        assert result.external_user_id == "ext-123"
        assert result.chat_id == "chat-1"

    def test_chat__llm_app_service_chat_called_once_with_the_request(self):
        # Arrange
        args = _make_args()
        # Act
        routes.chat(**args)
        # Assert — the response path is untouched by the new task.
        args["llm_app_service"].chat.assert_called_once_with(args["request"])

"""
routes.chat background memory scheduling Unit Tests.

The chat route takes `background_tasks: BackgroundTasks` and
`memory_app_service` (via Depends). After obtaining the result from
llm_app_service.chat(request), it extracts output = result["output"] and
schedules:

    background_tasks.add_task(
        memory_app_service.learn_from_message,
        request.external_user_id,
        request.message,
        output,
    )

Adjusted in Fase E (chat context compaction, plan §6.5): the route now schedules
a SECOND background task (context compaction) after this one, so `add_task` is no
longer called exactly once — these tests now assert that exactly ONE of the
scheduled tasks is `learn_from_message`, and that it is the FIRST. The compaction
task itself is covered by test_routes_chat_schedules_compaction.py.

This is a unit test: we call the `chat` function directly (no server), passing
mocks for llm_app_service, background_tasks, memory_app_service and
context_compaction_app_service.
"""

from unittest.mock import MagicMock

from application.appservices.view_models import ChatRequest
import routes


# ===========================================================================
# Helpers
# ===========================================================================


def _make_args(output="resposta", intent=None):
    llm_app_service = MagicMock()
    llm_app_service.chat.return_value = {
        "output": output,
        "intent": intent or ["only_talking"],
    }
    background_tasks = MagicMock()
    memory_app_service = MagicMock()
    context_compaction_app_service = MagicMock()
    request = ChatRequest(
        message="adoro café sem açúcar",
        external_user_id="ext-123",
        chat_id="chat-1",
    )
    return (
        request,
        llm_app_service,
        background_tasks,
        memory_app_service,
        context_compaction_app_service,
    )


def _scheduled_params(background_tasks):
    """Flatten every add_task call into a list of its args + kwargs values."""
    return [
        list(call.args) + list(call.kwargs.values())
        for call in background_tasks.add_task.call_args_list
    ]


# ===========================================================================
# TestChatSchedulesMemory
# ===========================================================================


class TestChatSchedulesMemory:
    def test_chat__schedules_learn_from_message_once(self):
        # Arrange
        request, llm, bg, memory, compaction = _make_args()
        # Act
        routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
            context_compaction_app_service=compaction,
        )
        # Assert — exactly one of the scheduled tasks is the memory extraction.
        scheduled = _scheduled_params(bg)
        assert (
            sum(1 for params in scheduled if memory.learn_from_message in params) == 1
        )

    def test_chat__schedules_memory_task_first(self):
        # Arrange — order is fixed by plan §6.5: memory reads the turn that was
        # just persisted; compaction may rewrite the head of the history.
        request, llm, bg, memory, compaction = _make_args()
        # Act
        routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
            context_compaction_app_service=compaction,
        )
        # Assert
        assert bg.add_task.call_args_list[0].args[0] is memory.learn_from_message

    def test_chat__schedules_with_correct_callable_and_args(self):
        # Arrange
        request, llm, bg, memory, compaction = _make_args(output="resposta")
        # Act
        routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
            context_compaction_app_service=compaction,
        )
        # Assert
        args, kwargs = bg.add_task.call_args_list[0]
        positional = list(args) + list(kwargs.values())
        assert memory.learn_from_message in positional
        assert "ext-123" in positional
        assert "adoro café sem açúcar" in positional
        assert "resposta" in positional


# ===========================================================================
# TestChatResponseContract
# ===========================================================================


class TestChatResponseContract:
    """
    The ChatResponse.response field is typed `str` and must carry the plain
    assistant text (result["output"]), not the whole {"intent":..,"output":..}
    dict returned by llm_app_service.chat().
    """

    def test_chat__response_field_is_output_string(self):
        # Arrange
        request, llm, bg, memory, compaction = _make_args(output="olá mundo")
        # Act
        result = routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
            context_compaction_app_service=compaction,
        )
        # Assert
        assert result.response == "olá mundo"
        assert isinstance(result.response, str)

    def test_chat__propagates_identifiers(self):
        # Arrange
        request, llm, bg, memory, compaction = _make_args()
        # Act
        result = routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
            context_compaction_app_service=compaction,
        )
        # Assert
        assert result.external_user_id == "ext-123"
        assert result.chat_id == "chat-1"

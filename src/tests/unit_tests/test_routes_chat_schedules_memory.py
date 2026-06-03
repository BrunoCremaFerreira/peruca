"""
routes.chat background memory scheduling Unit Tests (TDD - RED phase)

The chat route will gain `background_tasks: BackgroundTasks` and
`memory_app_service` (via Depends). After obtaining the result from
llm_app_service.chat(request), it must extract output = result["output"] and
schedule:

    background_tasks.add_task(
        memory_app_service.learn_from_message,
        request.external_user_id,
        request.message,
        output,
    )

This is a unit test: we call the `chat` function directly (no server), passing
mocks for llm_app_service, background_tasks and memory_app_service.

NOTE on current contract: today chat does
    response_str = llm_app_service.chat(request)
and returns ChatResponse(response=response_str, ...). The new chat extracts
output = result["output"]. These tests target the NEW contract and are expected
to FAIL (TypeError on extra kwargs, or AttributeError) until routes.py is
updated.
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
    request = ChatRequest(
        message="adoro café sem açúcar",
        external_user_id="ext-123",
        chat_id="chat-1",
    )
    return request, llm_app_service, background_tasks, memory_app_service


# ===========================================================================
# TestChatSchedulesMemory
# ===========================================================================


class TestChatSchedulesMemory:
    def test_chat__schedules_learn_from_message_once(self):
        # Arrange
        request, llm, bg, memory = _make_args()
        # Act
        routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
        )
        # Assert
        bg.add_task.assert_called_once()

    def test_chat__schedules_with_correct_callable_and_args(self):
        # Arrange
        request, llm, bg, memory = _make_args(output="resposta")
        # Act
        routes.chat(
            request=request,
            background_tasks=bg,
            llm_app_service=llm,
            memory_app_service=memory,
        )
        # Assert
        args, kwargs = bg.add_task.call_args
        positional = list(args) + list(kwargs.values())
        assert memory.learn_from_message in positional
        assert "ext-123" in positional
        assert "adoro café sem açúcar" in positional
        assert "resposta" in positional

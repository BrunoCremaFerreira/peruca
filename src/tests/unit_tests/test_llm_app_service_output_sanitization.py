"""
LlmAppService._persist_turn data URI sanitization Unit Tests (TDD RED).

F1 (cameras review plan §3.2): today ``_persist_turn`` writes
``AIMessage(content=output)`` verbatim. When the output carries a camera
snapshot data URI ("data:image/..." line), the multi-MB base64 is persisted
into the conversation history and reinjected into the OnlyTalkGraph
``MessagesPlaceholder("history")`` on the next turn — context explosion even
in single-intent turns.

Fix under test: the AIMessage written to history receives the SANITIZED text
(URI lines replaced by the "[snapshot da câmera exibido]" placeholder via
application/appservices/output_sanitizer.replace_image_data_uris), while the
HTTP response returned to the client keeps the URI intact — the URI is the
deliverable.

Follows the helper pattern of test_llm_app_service_history.py.
"""

import base64
import uuid
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User


_PLACEHOLDER = "[snapshot da câmera exibido]"


# ===========================================================================
# Helpers
# ===========================================================================


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _make_service(user=None, invoke_result=None):
    """
    Build a LlmAppService with all dependencies mocked.

    Returns (service, main_graph, get_session_history, history).
    """
    main_graph = MagicMock()
    main_graph.invoke.return_value = invoke_result or {
        "output": "ok",
        "intent": ["only_talking"],
    }

    context_repository = MagicMock()

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    history = MagicMock()
    get_session_history = MagicMock(return_value=history)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=context_repository,
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
    )
    return service, main_graph, get_session_history, history


def _png_data_uri() -> str:
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfake_png").decode()
    return f"data:image/png;base64,{encoded}"


def _written_ai_message(history: MagicMock) -> AIMessage:
    history.add_messages.assert_called_once()
    written = history.add_messages.call_args[0][0]
    assert len(written) == 2, f"Expected [Human, AI], got {len(written)} messages"
    ai = written[1]
    assert isinstance(ai, AIMessage), f"Expected AIMessage, got {type(ai)}"
    return ai


# ===========================================================================
# TestPersistTurnSanitizesDataUris
# ===========================================================================


class TestPersistTurnSanitizesDataUris:
    def test_persist_turn__output_with_data_uri__history_receives_placeholder_not_uri(
        self,
    ):
        """
        The AIMessage persisted to history must carry the placeholder instead
        of the data URI line; the other output lines survive intact.
        """
        user = _sample_user()
        service, _, _, history = _make_service(user=user)
        uri = _png_data_uri()
        output = f"{uri}\nCamera Sala: gravando"

        service._persist_turn(user=user, message="mostra a câmera", output=output)

        ai = _written_ai_message(history)
        assert "data:image/" not in ai.content, (
            f"Data URI leaked into the persisted history: {ai.content[:120]!r}"
        )
        assert _PLACEHOLDER in ai.content, (
            f"Expected the placeholder in the persisted AIMessage, "
            f"got: {ai.content[:120]!r}"
        )
        assert "Camera Sala: gravando" in ai.content, (
            f"Non-URI lines must survive in the persisted AIMessage, "
            f"got: {ai.content!r}"
        )

    def test_persist_turn__plain_output__unchanged(self):
        """An output with no data URI must be persisted byte-identical."""
        user = _sample_user()
        service, _, _, history = _make_service(user=user)
        output = "Liguei a luz da sala."

        service._persist_turn(user=user, message="acende a luz", output=output)

        ai = _written_ai_message(history)
        assert ai.content == output, (
            f"Plain output must be persisted unchanged, got: {ai.content!r}"
        )

    def test_chat__output_with_data_uri__http_response_keeps_uri_intact(self):
        """
        The sanitization is history-only: the chat() return value (the HTTP
        deliverable) must keep the data URI intact while the persisted
        AIMessage receives the placeholder.
        """
        user = _sample_user()
        uri = _png_data_uri()
        service, _, _, history = _make_service(
            user=user,
            invoke_result={
                "intent": ["smart_home_security_cams"],
                "output": uri,
            },
        )
        request = ChatRequest(
            message="mostra a câmera da sala",
            external_user_id=user.external_id,
            chat_id="c1",
        )

        result = service.chat(request)

        assert uri in result["output"], (
            "The HTTP response must keep the data URI intact — it is the "
            "deliverable."
        )
        ai = _written_ai_message(history)
        assert "data:image/" not in ai.content, (
            f"Data URI leaked into the persisted history: {ai.content[:120]!r}"
        )

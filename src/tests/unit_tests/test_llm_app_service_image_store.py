"""
LlmAppService image-store integration unit tests (TDD - RED phase, Fase B).

When an image store is available and the only_talk turn produced an image
description, chat() must:
  - obtain a stable per-user handle N (image_store.next_index),
  - save the blob BEFORE writing the history reference (atomicity: never a
    dangling #N),
  - persist the history line as "[Imagem #N enviada pelo usuário: <desc>]".
On save failure (or no store) it degrades to the handle-less line
"[Imagem enviada pelo usuário: <desc>]" without aborting the turn.

Expected to FAIL until LlmAppService is wired to the image store.
"""

import uuid
from unittest.mock import MagicMock, call

from application.appservices.llm_app_service import LlmAppService
from application.appservices.view_models import ChatRequest
from domain.entities import User


VALID_PNG = "data:image/png;base64,aGVsbG8="
VALID_JPEG = "data:image/jpeg;base64,d29ybGQ="


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


def _make_service(user, graph_result, image_store=None):
    main_graph = MagicMock()
    main_graph.invoke.return_value = graph_result

    user_repository = MagicMock()
    user_repository.get_by_external_id.return_value = user

    user_memory_service = MagicMock()
    user_memory_service.get_all_by_user.return_value = []

    history = MagicMock()
    get_session_history = MagicMock(return_value=history)

    service = LlmAppService(
        main_graph=main_graph,
        context_repository=MagicMock(),
        user_repository=user_repository,
        user_memory_service=user_memory_service,
        get_session_history=get_session_history,
        image_store=image_store,
    )
    return service, history


def _human_content(history):
    messages = history.add_messages.call_args[0][0]
    return messages[0].content


class TestLlmAppServiceImageStore:
    def test_saves_blob_and_writes_handle_in_history(self):
        user = _sample_user()
        store = MagicMock()
        store.next_index.return_value = 1
        service, history = _make_service(
            user,
            {"output": "Que gato!", "intent": ["only_talking"],
             "image_description": "Um gato preto."},
            image_store=store,
        )
        request = ChatRequest(
            message="o que é isso?", external_user_id=user.external_id,
            images=[VALID_PNG],
        )

        service.chat(request)

        store.save.assert_called_once_with(user.id, "1", VALID_PNG)
        assert "[Imagem #1 enviada pelo usuário: Um gato preto.]" in _human_content(
            history
        )

    def test_saves_blob_before_history_reference(self):
        user = _sample_user()
        recorder = MagicMock()
        store = MagicMock()
        store.next_index.return_value = 1
        store.save.side_effect = lambda *a, **k: recorder("save")
        service, history = _make_service(
            user,
            {"output": "ok", "intent": ["only_talking"],
             "image_description": "desc"},
            image_store=store,
        )
        history.add_messages.side_effect = lambda *a, **k: recorder("history")
        request = ChatRequest(
            message="olha", external_user_id=user.external_id, images=[VALID_PNG]
        )

        service.chat(request)

        assert recorder.call_args_list == [call("save"), call("history")]

    def test_multiple_images_get_distinct_handles(self):
        user = _sample_user()
        store = MagicMock()
        store.next_index.side_effect = [1, 2]
        service, history = _make_service(
            user,
            {"output": "ok", "intent": ["only_talking"],
             "image_description": "duas fotos"},
            image_store=store,
        )
        request = ChatRequest(
            message="olha essas", external_user_id=user.external_id,
            images=[VALID_PNG, VALID_JPEG],
        )

        service.chat(request)

        assert store.save.call_args_list == [
            call(user.id, "1", VALID_PNG),
            call(user.id, "2", VALID_JPEG),
        ]
        content = _human_content(history)
        assert "#1" in content and "#2" in content

    def test_save_failure_degrades_without_handle_and_does_not_raise(self):
        user = _sample_user()
        store = MagicMock()
        store.next_index.return_value = 1
        store.save.side_effect = RuntimeError("redis down")
        service, history = _make_service(
            user,
            {"output": "ok", "intent": ["only_talking"],
             "image_description": "um gato"},
            image_store=store,
        )
        request = ChatRequest(
            message="olha", external_user_id=user.external_id, images=[VALID_PNG]
        )

        service.chat(request)  # must not raise

        content = _human_content(history)
        assert "#" not in content
        assert "[Imagem enviada pelo usuário: um gato]" in content

    def test_no_store__no_handle_in_history(self):
        user = _sample_user()
        service, history = _make_service(
            user,
            {"output": "ok", "intent": ["only_talking"],
             "image_description": "um gato"},
            image_store=None,
        )
        request = ChatRequest(
            message="olha", external_user_id=user.external_id, images=[VALID_PNG]
        )

        service.chat(request)

        content = _human_content(history)
        assert "#" not in content
        assert "[Imagem enviada pelo usuário: um gato]" in content


class TestLlmAppServiceRevisionEnrichment:
    def test_revision_turn_persists_enriched_description_under_handle(self):
        # A text-only follow-up (no new images) that re-visited image #3 must
        # persist the refreshed description under #3 so future turns stay cheap.
        user = _sample_user()
        store = MagicMock()
        service, history = _make_service(
            user,
            {
                "output": "O número é XYZ-123.",
                "intent": ["only_talking"],
                "image_description": "Documento com número de série XYZ-123.",
                "revised_image_index": "3",
            },
            image_store=store,
        )
        request = ChatRequest(
            message="qual o número de série?", external_user_id=user.external_id,
            images=[],
        )

        service.chat(request)

        # No new blob saved (no new images this turn).
        store.save.assert_not_called()
        content = _human_content(history)
        assert (
            "[Imagem #3 enviada pelo usuário: Documento com número de série XYZ-123.]"
            in content
        )

    def test_no_revision_index__plain_follow_up_history(self):
        user = _sample_user()
        store = MagicMock()
        service, history = _make_service(
            user,
            {"output": "Claro!", "intent": ["only_talking"],
             "image_description": None, "revised_image_index": None},
            image_store=store,
        )
        request = ChatRequest(
            message="e aí?", external_user_id=user.external_id, images=[]
        )

        service.chat(request)

        content = _human_content(history)
        assert content == "e aí?"

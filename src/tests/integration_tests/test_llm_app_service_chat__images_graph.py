"""
LlmAppService Integration Tests — Multimodal image input (Fases A, B, C).

Requires a live Ollama serving a multimodal gemma4 (LLM_PROVIDER_URL) for the
vision/routing tests; the validation error-path tests raise before any LLM call
and the persistence tests additionally require the test Redis.

Following the project convention for hardware-dependent flows, the LLM-driven
tests assert only routing and non-empty output (never a specific visual
content, which the model produces nondeterministically).
"""

import os

import pytest
from redis import from_url

from application.appservices.view_models import ChatRequest
from domain.exceptions import ValidationError
from infra.ioc import get_image_store, get_user_repository


pytestmark = pytest.mark.integration


# A real, valid 64x64 PNG (yellow square on a blue background) as a data URI.
# A larger-than-trivial image is required: Ollama's vision preprocessor rejects
# degenerate 1x1 images ("Failed to load image"). We never assert on its content
# (the model describes it nondeterministically) — only on routing/output.
IMAGE_TEST_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAW0lEQVR42u3ZQQ0AIAwAsYngjbApnhwkoAIySJMz0PfFzHq6AAAAAAAAAAAAAAC4Blg1jgYAAAAAAAAAAAAAAAAAAAAAAAAAAAAA0A/g0AAAAAAAAAAAAAB8A9gG7zFLt4pzJAAAAABJRU5ErkJggg=="  # noqa: E501

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


# ======================================================
# Fase A — Vision routing + non-empty output (needs Ollama)
# ======================================================


def test_chat__empty_text_with_image__routes_only_talking(
    llm_app_service, integration_user
):
    # Text-empty + image short-circuits to free conversation.
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message="",
        images=[IMAGE_TEST_PNG],
    )

    response = llm_app_service.chat(chat_request=chat_request)

    assert response.get("intents") == ["only_talking"]
    assert response.get("output")


@pytest.mark.parametrize(
    "message",
    [
        "O que você vê nesta imagem?",
        "Descreve essa foto pra mim.",
        "Que imagem é essa que te mandei?",
    ],
)
def test_chat__visual_question_with_image__routes_only_talking(
    message, llm_app_service, integration_user
):
    chat_request = ChatRequest(
        external_user_id=integration_user.external_id,
        message=message,
        images=[IMAGE_TEST_PNG],
    )

    response = llm_app_service.chat(chat_request=chat_request)

    assert "only_talking" in response.get("intents")
    assert response.get("output")


# ======================================================
# Fase A — Input validation (raises before any LLM call)
# ======================================================


class TestChatImageValidation:
    def test_malformed_base64__raises_validation_error(
        self, llm_app_service, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="olha",
            images=["data:image/png;base64,@@@not-base64@@@"],
        )
        with pytest.raises(ValidationError):
            llm_app_service.chat(chat_request=chat_request)

    def test_unsupported_mime__raises_validation_error(
        self, llm_app_service, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="olha",
            images=["data:image/gif;base64,aGVsbG8="],
        )
        with pytest.raises(ValidationError):
            llm_app_service.chat(chat_request=chat_request)

    def test_not_a_data_uri__raises_validation_error(
        self, llm_app_service, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="olha",
            images=["aGVsbG8="],
        )
        with pytest.raises(ValidationError):
            llm_app_service.chat(chat_request=chat_request)

    def test_oversized_image__raises_validation_error(
        self, llm_app_service, integration_user
    ):
        # ~8 MiB of base64 estimates well above the 5 MiB default cap; must be
        # rejected WITHOUT decoding (DoS guard) and before any LLM call.
        oversized = "data:image/png;base64," + ("A" * (8 * 1024 * 1024))
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="olha",
            images=[oversized],
        )
        with pytest.raises(ValidationError):
            llm_app_service.chat(chat_request=chat_request)


# ======================================================
# Fase B — Blob stored + description persisted, base64 never in history
# (needs Ollama + Redis)
# ======================================================


class TestChatImagePersistence:
    def _user_id(self, external_id: str) -> str:
        user = get_user_repository().get_by_external_id(external_id)
        return user.id

    def test_image_turn__blob_stored_in_image_store(
        self, llm_app_service_redis, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="o que é isso?",
            images=[IMAGE_TEST_PNG],
        )

        llm_app_service_redis.chat(chat_request=chat_request)

        user_id = self._user_id(integration_user.external_id)
        stored = get_image_store().get(user_id, "1")
        assert stored == IMAGE_TEST_PNG

    def test_image_turn__history_has_description_not_base64(
        self, llm_app_service_redis, integration_user
    ):
        chat_request = ChatRequest(
            external_user_id=integration_user.external_id,
            message="o que é isso?",
            images=[IMAGE_TEST_PNG],
        )

        llm_app_service_redis.chat(chat_request=chat_request)

        user_id = self._user_id(integration_user.external_id)
        client = from_url(TEST_REDIS_URL)
        try:
            raw = client.get(f"chat_history:{user_id}")
        finally:
            client.close()
        text = raw.decode("utf-8") if raw else ""

        assert text, "the turn must have been persisted to history"
        # The description line marks the image; the base64 never leaks.
        assert "Imagem" in text
        assert "data:image" not in text
        assert "iVBORw0KGgo" not in text  # the PNG base64 signature


# ======================================================
# Fase C — Re-vision smoke test (needs Ollama + Redis)
#
# The re-vision gate is model-driven (the LLM decides whether to emit the
# sentinel), so we cannot deterministically force it here — the exhaustive gate
# logic is covered by unit tests. This smoke test only asserts the end-to-end
# follow-up path runs without error and keeps producing output.
# ======================================================


class TestChatImageRevisionSmoke:
    def test_image_then_detail_followup__both_turns_produce_output(
        self, llm_app_service_redis, integration_user
    ):
        first = ChatRequest(
            external_user_id=integration_user.external_id,
            message="Olha essa foto.",
            images=[IMAGE_TEST_PNG],
        )
        followup = ChatRequest(
            external_user_id=integration_user.external_id,
            message="E qual a cor exata do que aparece na foto?",
            images=[],
        )

        first_response = llm_app_service_redis.chat(chat_request=first)
        followup_response = llm_app_service_redis.chat(chat_request=followup)

        assert first_response.get("output")
        assert followup_response.get("output")
        assert "only_talking" in followup_response.get("intents")

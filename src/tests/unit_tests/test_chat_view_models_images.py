"""
ChatRequest images field unit tests (TDD - RED phase).

Fase A of the multimodal-image plan adds an `images: list[str]` field (data
URIs) to ChatRequest, defaulting to an empty list so every existing positional
construction stays valid. ChatResponse must remain unchanged (the assistant
does not return images).

Expected to FAIL (TypeError / AttributeError) until the field is added.
"""

from dataclasses import fields

from application.appservices.view_models import ChatRequest, ChatResponse


class TestChatRequestImagesField:
    def test_default_images_is_empty_list(self):
        request = ChatRequest()
        assert request.images == []

    def test_default_is_a_distinct_list_per_instance(self):
        a = ChatRequest()
        b = ChatRequest()
        a.images.append("data:image/png;base64,AAAA")
        assert b.images == []

    def test_legacy_positional_construction_still_valid(self):
        # message, external_user_id, chat_id — the pre-existing positional order.
        request = ChatRequest("oi", "ext-1", "chat-1")
        assert request.message == "oi"
        assert request.external_user_id == "ext-1"
        assert request.chat_id == "chat-1"
        assert request.images == []

    def test_stores_provided_images(self):
        uris = ["data:image/jpeg;base64,AAAA", "data:image/png;base64,BBBB"]
        request = ChatRequest(message="olha isso", images=uris)
        assert request.images == uris


class TestChatResponseUnchanged:
    def test_chat_response_has_no_images_field(self):
        names = {f.name for f in fields(ChatResponse)}
        assert "images" not in names
        assert names == {"response", "external_user_id", "chat_id"}

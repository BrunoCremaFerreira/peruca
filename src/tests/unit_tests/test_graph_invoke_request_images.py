"""
GraphInvokeRequest images field unit tests (TDD - RED phase).

Fase A adds `images: list[str]` (data URIs) to GraphInvokeRequest, default empty
so every existing construction (`message`/`user` positional/keyword) stays valid.

Expected to FAIL until the field is added.
"""

import uuid

from domain.entities import GraphInvokeRequest, User


def _sample_user() -> User:
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="")


class TestGraphInvokeRequestImagesField:
    def test_default_images_is_empty_list(self):
        request = GraphInvokeRequest(message="oi", user=_sample_user())
        assert request.images == []

    def test_distinct_list_per_instance(self):
        a = GraphInvokeRequest(message="a", user=_sample_user())
        b = GraphInvokeRequest(message="b", user=_sample_user())
        a.images.append("data:image/png;base64,AAAA")
        assert b.images == []

    def test_legacy_construction_message_user_still_valid(self):
        user = _sample_user()
        request = GraphInvokeRequest(message="oi", user=user, memories=["m"])
        assert request.message == "oi"
        assert request.user is user
        assert request.memories == ["m"]
        assert request.images == []

    def test_stores_provided_images(self):
        uris = ["data:image/jpeg;base64,AAAA"]
        request = GraphInvokeRequest(
            message="olha", user=_sample_user(), images=uris
        )
        assert request.images == uris

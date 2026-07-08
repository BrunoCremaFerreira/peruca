"""
ReadOnlyPetRepository (§2.4 nível 1): the object handed to the chat path must
PHYSICALLY lack write methods, so no reachable code can mutate pets via chat.
"""

from unittest.mock import MagicMock

from domain.entities import Pet
from domain.interfaces.pet_repository import PetRepository
from infra.data.read_only_pet_repository import ReadOnlyPetRepository


def _inner():
    inner = MagicMock()
    inner.get_by_id.return_value = Pet(id="p1", user_id="u1", name="Caçolin")
    inner.get_all_by_user_id.return_value = [Pet(id="p1", user_id="u1", name="Caçolin")]
    return inner


class TestReadOnly:
    def test_delegates_reads(self):
        inner = _inner()
        repo = ReadOnlyPetRepository(inner)
        assert repo.get_by_id("p1").id == "p1"
        assert len(repo.get_all_by_user_id("u1")) == 1
        inner.get_by_id.assert_called_once_with("p1")
        inner.get_all_by_user_id.assert_called_once_with("u1")

    def test_has_no_write_methods(self):
        repo = ReadOnlyPetRepository(_inner())
        assert not hasattr(repo, "add")
        assert not hasattr(repo, "update")
        assert not hasattr(repo, "delete")

    def test_is_not_a_write_repository(self):
        repo = ReadOnlyPetRepository(_inner())
        assert not isinstance(repo, PetRepository)

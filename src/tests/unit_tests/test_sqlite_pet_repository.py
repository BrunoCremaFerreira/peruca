"""
SqlitePetRepository tests (TDD) — REAL temporary SQLite DB via sqlite_db_path.

Covers add/get round-trip, the nicknames JSON serialization with order preserved
(1st = primary), empty nickname list, per-user isolation, update and delete.
"""

import uuid
from datetime import date, datetime, timezone

from domain.entities import Pet
from infra.data.sqlite.sqlite_pet_repository import SqlitePetRepository


def _make_repo(sqlite_db_path) -> SqlitePetRepository:
    return SqlitePetRepository(db_path=f"sqlite://{sqlite_db_path}")


def _sample(user_id, name="Caçolin", nicknames=None, birth_date=date(2020, 1, 1),
            sex="male", species="dog", description="preguiçoso") -> Pet:
    return Pet(
        id=str(uuid.uuid4()), user_id=user_id, name=name,
        nicknames=list(nicknames) if nicknames is not None else ["Lilo", "Suzu"],
        birth_date=birth_date, sex=sex, species=species, description=description,
        when_created=datetime.now(timezone.utc),
    )


class TestSqlitePetRepository:
    def test_add_then_get_by_id__returns_entity(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()))
        repo.add(pet)

        loaded = repo.get_by_id(pet.id)
        assert loaded is not None
        assert loaded.id == pet.id
        assert loaded.name == "Caçolin"
        assert loaded.birth_date == date(2020, 1, 1)
        assert loaded.sex == "male"
        assert loaded.species == "dog"
        assert loaded.description == "preguiçoso"

    def test_nicknames_roundtrip_preserves_order(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()), nicknames=["Lilo", "Caçolinho", "Suzu"])
        repo.add(pet)

        loaded = repo.get_by_id(pet.id)
        assert loaded.nicknames == ["Lilo", "Caçolinho", "Suzu"]
        assert loaded.nicknames[0] == "Lilo"  # primary

    def test_empty_nicknames_roundtrip(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()), nicknames=[])
        repo.add(pet)

        loaded = repo.get_by_id(pet.id)
        assert loaded.nicknames == []

    def test_none_birth_date_roundtrip(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()), birth_date=None)
        repo.add(pet)
        assert repo.get_by_id(pet.id).birth_date is None

    def test_get_all_by_user_id__isolates_users(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
        repo.add(_sample(user_a, name="Caçolin"))
        repo.add(_sample(user_b, name="Caçolão", nicknames=["Lyon"]))

        a_pets = repo.get_all_by_user_id(user_a)
        assert len(a_pets) == 1
        assert all(p.user_id == user_a for p in a_pets)

    def test_update__persists_changes(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()))
        repo.add(pet)
        pet.description = "adora o sofá"
        pet.nicknames = ["Lilo"]
        repo.update(pet)

        loaded = repo.get_by_id(pet.id)
        assert loaded.description == "adora o sofá"
        assert loaded.nicknames == ["Lilo"]

    def test_delete__removes_pet(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        pet = _sample(str(uuid.uuid4()))
        repo.add(pet)
        repo.delete(pet.id)
        assert repo.get_by_id(pet.id) is None

    def test_get_by_id_missing__returns_none(self, sqlite_db_path):
        repo = _make_repo(sqlite_db_path)
        assert repo.get_by_id(str(uuid.uuid4())) is None

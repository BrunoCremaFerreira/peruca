import asyncio
import os
from unittest.mock import MagicMock, patch
import pytest

from infra.ioc import get_user_app_service, get_user_repository


DB_PATH = "/home/brn/tests/data/tests.db"


@pytest.fixture(autouse=True)
def fresh_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture
def user_repo_mock():
    repo = MagicMock()
    repo.get_by_id.return_value = None
    repo.get_by_external_id.return_value = None
    return repo


@pytest.fixture
def shopping_list_repo_mock():
    repo = MagicMock()
    repo.get_by_name.return_value = None
    repo.get_by_id.return_value = None
    return repo


@pytest.fixture
def sqlite_db_path():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    yield DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest.fixture
def user_app_service_with_db(sqlite_db_path):
    with patch.dict(
        os.environ,
        {
            "PERUCA_DB_CONNECTION_STRING": f"sqlite://{sqlite_db_path}",
        },
    ):
        repo = get_user_repository()
        app_service = get_user_app_service()
        yield app_service, repo
        repo.close()

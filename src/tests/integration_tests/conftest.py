import os
from unittest.mock import patch
import pytest

from domain.commands import UserAdd
from infra.ioc import (
    get_llm_app_service,
    get_shopping_list_repository,
    get_user_app_service,
)


# Each pytest-xdist worker gets an isolated SQLite file so parallel runs do not
# delete each other's database. Serial runs (no xdist) keep a single file.
# The DB lives in tmpfs (/dev/shm) so the per-test remove/recreate cycle does
# not pay real disk latency between tests (the GPU sits idle during setup).
_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
DB_PATH = f"/dev/shm/peruca_tests{('_' + _worker) if _worker else ''}.db"

INTEGRATION_ENV = {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://unix.rtx-server:11434",
    "LLM_PROVIDER_API_KEY": "fake-api-key",
    "LLM_MAIN_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_MAIN_GRAPH_CHAT_TEMPERATURE": "0.1",
    "LLM_ONLY_TALK_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_ONLY_TALK_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_SHOPPING_LIST_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_SHOPPING_LIST_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_SMART_HOME_CLIMATE_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_SMART_HOME_CLIMATE_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_MUSIC_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_MUSIC_GRAPH_CHAT_TEMPERATURE": "0.3",
    "LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_MODEL": "gemma4:12b",
    "LLM_VEHICLE_MAINTENANCE_GRAPH_CHAT_TEMPERATURE": "0.1",
    "MUSIC_ASSISTANT_URL": "http://unix.rtx-server:8095",
    "MUSIC_ASSISTANT_TOKEN": "",
    "NLP_SPACY_MODEL": "pt_core_news_sm",
    "HOME_ASSISTANT_URL": "unix.kubernetes:8123",
    "CACHE_DB_CONNECTION_STRING": "",
    "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
}


@pytest.fixture(scope="session")
def integration_env():
    with patch.dict(os.environ, INTEGRATION_ENV):
        yield


@pytest.fixture
def integration_db_path(integration_env):
    with patch.dict(os.environ, {"PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}"}):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        yield DB_PATH
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)


@pytest.fixture
def user_app_service(integration_db_path):
    return get_user_app_service()


@pytest.fixture
def integration_user(user_app_service):
    user_cmd = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user_cmd)
    return user_cmd


@pytest.fixture
def llm_app_service(integration_user, integration_db_path):
    return get_llm_app_service()


@pytest.fixture
def shopping_list_repo_for_integration(integration_db_path):
    return get_shopping_list_repository()


# ---------------------------------------------------------------------------
# Redis-backed conversation history
#
# The OnlyTalkGraph history tests must exercise the real Redis persistence
# path, not the in-memory fallback. They point CACHE_DB_CONNECTION_STRING at a
# dedicated test Redis (DB index 15 by default, overridable via TEST_REDIS_URL)
# and skip gracefully when no Redis server is reachable, so the suite stays
# green in environments without Redis.
# ---------------------------------------------------------------------------
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


def _clear_history_keys(connection_string: str) -> None:
    from redis import from_url

    client = from_url(connection_string)
    try:
        for pattern in (
            "chat_history:*",
            "image:*",
            "image_ids:*",
            "image_seq:*",
        ):
            for key in client.scan_iter(pattern):
                client.delete(key)
    finally:
        client.close()


@pytest.fixture
def redis_backed_env(integration_env):
    from redis import from_url
    from redis.exceptions import RedisError

    client = from_url(TEST_REDIS_URL)
    try:
        client.ping()
    except (RedisError, OSError) as exc:
        pytest.skip(f"Test Redis not reachable at {TEST_REDIS_URL}: {exc}")
    finally:
        client.close()

    import infra.ioc as ioc

    with patch.dict(os.environ, {"CACHE_DB_CONNECTION_STRING": TEST_REDIS_URL}):
        # Changing the environment invalidates the cached IoC graphs (the
        # session-history factory captures the Redis repo at build time), so the
        # graph must be rebuilt with the Redis-backed factory.
        ioc._repo_cache.clear()
        _clear_history_keys(TEST_REDIS_URL)
        yield TEST_REDIS_URL
        _clear_history_keys(TEST_REDIS_URL)
        ioc._repo_cache.clear()


@pytest.fixture
def llm_app_service_redis(redis_backed_env, integration_user, integration_db_path):
    return get_llm_app_service()

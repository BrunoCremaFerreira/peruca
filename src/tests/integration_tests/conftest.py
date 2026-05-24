import os
from unittest.mock import patch
import pytest

from domain.commands import UserAdd
from infra.ioc import get_llm_app_service, get_user_app_service


DB_PATH = "/home/brn/tests/data/tests.db"

INTEGRATION_ENV = {
    "CORS_ORIGIN": "http://localhost:3000",
    "LLM_PROVIDER_TYPE": "OLLAMA",
    "LLM_PROVIDER_URL": "http://unix.rtx-server:11434",
    "LLM_PROVIDER_API_KEY": "fake-api-key",
    "LLM_MAIN_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_MAIN_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_ONLY_TALK_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_ONLY_TALK_GRAPH_CHAT_TEMPERATURE": "0.5",
    "LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_MODEL": "qwen3:14b",
    "LLM_SMART_HOME_LIGHTS_GRAPH_CHAT_TEMPERATURE": "0.5",
    "NLP_SPACY_MODEL": "pt_core_news_sm",
    "HOME_ASSISTANT_URL": "unix.kubernetes:8123",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
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
def llm_app_service(integration_db_path):
    return get_llm_app_service()


@pytest.fixture
def integration_user(user_app_service):
    user_cmd = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user_cmd)
    return user_cmd

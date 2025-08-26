

import os
from unittest.mock import patch

import pytest

from application.appservices.view_models import ChatRequest
from domain.commands import UserAdd
from infra.ioc import get_llm_app_service, get_user_app_service


DB_PATH = "/home/brn/tests/data/tests.db"
@patch.dict(os.environ, {
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
})

def setup_app_service():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return get_llm_app_service(), get_user_app_service()

@pytest.mark.parametrize("message, expected_items", [
    ("ligue a luz da sala", ["luz da sala"]),
    ("ligue o abajur do quarto", ["abajur do quarto"])
])
def test_chat_smart_home_lights__turn_on(message, expected_items):
    # Arrange
    llm_app_service, user_app_service = setup_app_service()
    user = UserAdd(name="Bruno", external_id="1000", summary="")
    user_app_service.add(user)
    chat_request = ChatRequest(external_user_id=user.external_id, message=message)

    # Act
    response = llm_app_service.chat(chat_request=chat_request)
    intents = response.get("intents")
    output = response.get("output")

    # Assert
    assert "turn_on" in intents
    for item in expected_items:
        assert item in output
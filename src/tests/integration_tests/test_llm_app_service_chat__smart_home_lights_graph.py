

import os
from unittest.mock import patch

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
    "NLP_SPACY_MODEL": "pt_core_news_sm",
    "CACHE_DB_CONNECTION_STRING": "redis://localhost:6379/0",
    "PERUCA_DB_CONNECTION_STRING": f"sqlite://{DB_PATH}",
})

def setup_app_service():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return get_llm_app_service(), get_user_app_service()
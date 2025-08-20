from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Environment Config
    """

    # ===============================
    # API Config
    # ===============================

    cors_origin: str = "*"

    # ===============================
    # LLM Provider Configs
    # ===============================

    llm_provider_type: str = "OLLAMA"
    llm_provider_url: str = "http://10.10.1.10:11434"
    llm_provider_api_key: str = ""

    # ===============================
    # LLM Models config
    # ===============================

    llm_main_graph_chat_model: str = "qwen3:14b"
    llm_main_graph_chat_temperature: float = 0.5

    llm_only_talk_graph_chat_model: str = "qwen3:14b"
    llm_only_talk_graph_chat_temperature: float = 0.5

    llm_shopping_list_graph_chat_model: str = "qwen3:14b"
    llm_shopping_list_graph_chat_temperature: float = 0.5

    llm_smart_home_lights_graph_chat_model: str = "qwen3:14b"
    llm_smart_home_lights_graph_chat_temperature: float = 0.5


    # ===============================
    # NLP Models config
    # ===============================

    nlp_spacy_model: str = "pt_core_news_sm"

    # ===============================
    # Home Assistant Config
    # ===============================
    home_assistant_url: str = "http://localhost:8123"
    home_assistant_token: str = ""

    # ===============================
    # Databases Config
    # ===============================

    cache_db_connection_string: str = ""
    peruca_db_connection_string: str = (
        "sqlite:///peruca.db"
    )

from pathlib import Path

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
    # Intent classification must be near-deterministic — keep it low like the
    # other classifier graphs (sensors/cameras at 0.1). Higher values made
    # borderline commands flap between runs.
    llm_main_graph_chat_temperature: float = 0.1

    llm_only_talk_graph_chat_model: str = "qwen3:14b"
    llm_only_talk_graph_chat_temperature: float = 0.5

    llm_shopping_list_graph_chat_model: str = "qwen3:14b"
    llm_shopping_list_graph_chat_temperature: float = 0.5

    llm_smart_home_lights_graph_chat_model: str = "qwen3:14b"
    llm_smart_home_lights_graph_chat_temperature: float = 0.5

    llm_smart_home_climate_graph_chat_model: str = "qwen3:14b"
    llm_smart_home_climate_graph_chat_temperature: float = 0.5

    llm_smart_home_sensors_graph_chat_model: str = "qwen3:14b"
    llm_smart_home_sensors_graph_chat_temperature: float = 0.1

    llm_smart_home_cameras_graph_chat_model: str = "qwen3:14b"
    llm_smart_home_cameras_graph_chat_temperature: float = 0.1

    llm_memory_graph_chat_model: str = "qwen3:14b"
    llm_memory_graph_chat_temperature: float = 0.1

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
    # Music Assistant Config
    # ===============================

    music_assistant_url: str = "http://localhost:8095"
    music_assistant_token: str = ""
    llm_music_graph_chat_model: str = "qwen3:14b"
    llm_music_graph_chat_temperature: float = 0.3

    # ===============================
    # Databases Config
    # ===============================

    cache_db_connection_string: str = ""
    peruca_db_connection_string: str = (
        f"sqlite://{Path(__file__).parent.parent / 'peruca.db'}"
    )

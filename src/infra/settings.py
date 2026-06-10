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
    llm_strip_think_directive: bool = True

    # Keep the model resident in the Ollama VRAM between requests. Integer
    # seconds: -1 keeps it loaded indefinitely, 0 unloads immediately, e.g.
    # 1800 for 30 min. Must be an int — Ollama rejects the string "-1" with
    # "missing unit in duration".
    llm_keep_alive: int = -1
    # Context window; the Ollama default of 4096 truncates large prompts.
    llm_num_ctx: int = 8192
    # Token generation cap; -1 means no limit (neutral default).
    llm_num_predict: int = -1
    # Reasoning/thinking mode for the model. None = omit the `think` param
    # (safe default for models that reject it); False = disable thinking
    # (gemma4 — avoids ~350-500 wasted reasoning tokens per call); True = enable.
    llm_reasoning: bool | None = None

    # ===============================
    # LLM Models config
    # ===============================

    llm_main_graph_chat_model: str = "gemma4:12b"
    # Intent classification must be near-deterministic — keep it low like the
    # other classifier graphs (sensors/cameras at 0.1). Higher values made
    # borderline commands flap between runs.
    llm_main_graph_chat_temperature: float = 0.1
    # Per-graph reasoning override; None inherits the global `llm_reasoning`.
    llm_main_graph_chat_reasoning: bool | None = None

    llm_only_talk_graph_chat_model: str = "gemma4:12b"
    llm_only_talk_graph_chat_temperature: float = 0.5
    llm_only_talk_graph_chat_reasoning: bool | None = None

    llm_shopping_list_graph_chat_model: str = "gemma4:12b"
    llm_shopping_list_graph_chat_temperature: float = 0.5
    llm_shopping_list_graph_chat_reasoning: bool | None = None

    llm_smart_home_lights_graph_chat_model: str = "gemma4:12b"
    llm_smart_home_lights_graph_chat_temperature: float = 0.5
    llm_smart_home_lights_graph_chat_reasoning: bool | None = None

    llm_smart_home_climate_graph_chat_model: str = "gemma4:12b"
    llm_smart_home_climate_graph_chat_temperature: float = 0.1
    llm_smart_home_climate_graph_chat_reasoning: bool | None = None

    llm_smart_home_sensors_graph_chat_model: str = "gemma4:12b"
    llm_smart_home_sensors_graph_chat_temperature: float = 0.1
    llm_smart_home_sensors_graph_chat_reasoning: bool | None = None

    llm_smart_home_cameras_graph_chat_model: str = "gemma4:12b"
    llm_smart_home_cameras_graph_chat_temperature: float = 0.1
    llm_smart_home_cameras_graph_chat_reasoning: bool | None = None

    llm_memory_graph_chat_model: str = "gemma4:12b"
    llm_memory_graph_chat_temperature: float = 0.1
    llm_memory_graph_chat_reasoning: bool | None = None

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
    llm_music_graph_chat_model: str = "gemma4:12b"
    llm_music_graph_chat_temperature: float = 0.3
    llm_music_graph_chat_reasoning: bool | None = None

    # ===============================
    # Databases Config
    # ===============================

    cache_db_connection_string: str = ""
    peruca_db_connection_string: str = (
        f"sqlite://{Path(__file__).parent.parent / 'peruca.db'}"
    )

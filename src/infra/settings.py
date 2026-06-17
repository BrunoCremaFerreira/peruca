from pathlib import Path

from pydantic import field_validator
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
    # Reasoning/thinking mode for the model. False (default) disables thinking
    # so the configured gemma4 model stops emitting ~350-500 wasted reasoning
    # tokens per call (the dominant /chat latency cost). True enables it. Set
    # to empty (LLM_REASONING=) to omit the `think` param entirely — needed
    # only for models that reject it. Per-graph overrides win when not None.
    llm_reasoning: bool | None = False

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
    chat_history_ttl_seconds: int | None = None
    peruca_db_connection_string: str = (
        f"sqlite://{Path(__file__).parent.parent / 'peruca.db'}"
    )

    @field_validator("chat_history_ttl_seconds", mode="before")
    @classmethod
    def _empty_ttl_means_none(cls, value):
        # `.env.example` ships `CHAT_HISTORY_TTL_SECONDS=` (empty). An empty or
        # blank value must be read as "unset" (None) instead of failing int
        # parsing and crashing Settings() construction.
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

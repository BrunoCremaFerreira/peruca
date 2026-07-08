from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Environment Config
    """

    # ===============================
    # API Config
    # ===============================

    cors_origin: str = "*"
    log_level: str = "INFO"
    # Static API key for the REST API (header X-API-Key). Empty = migration mode:
    # the API stays open and a warning is logged at startup. Set it to require
    # the key on every route except /health. SecretStr keeps it out of logs/repr.
    peruca_api_key: SecretStr = SecretStr("")

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

    # Vehicle maintenance classifier: near-deterministic like the other
    # classifier graphs. Default to the same model so it stays VRAM-resident.
    llm_vehicle_maintenance_graph_chat_model: str = "gemma4:12b"
    llm_vehicle_maintenance_graph_chat_temperature: float = 0.1
    llm_vehicle_maintenance_graph_chat_reasoning: bool | None = None

    # Pet health classifier: near-deterministic like the other classifier graphs.
    llm_pet_health_graph_chat_model: str = "gemma4:12b"
    llm_pet_health_graph_chat_temperature: float = 0.1
    llm_pet_health_graph_chat_reasoning: bool | None = None

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
    # ===============================
    # Chat Image Input Config
    # ===============================
    # Limits for inbound base64 images on POST /llm/chat. Enforced by
    # ImageValidator BEFORE any LLM call (fail-fast, DoS guard). max_bytes is
    # the decoded-image ceiling; max_count caps images per request; allowed
    # mimes is the accepted allowlist.
    chat_image_max_bytes: int = 5_242_880  # 5 MiB
    chat_image_max_count: int = 4
    chat_image_allowed_mimes: list[str] = ["image/jpeg", "image/png", "image/webp"]
    # Image blob store (Fase B): keeps base64 out of the history but available
    # for on-demand re-vision. TTL bounds RAM (base64 is heavy); 24h covers
    # re-vision through the day and expires idle blobs. max_per_user is the
    # second RAM-containment axis (cap of images kept per user).
    chat_image_store_ttl_seconds: int = 86_400  # 24h
    chat_image_store_max_per_user: int = 10
    # How long (seconds) a pending shopping-list disambiguation question stays
    # valid before the stored state is treated as expired and discarded.
    disambiguation_ttl_seconds: int = 120
    # How long a pending multi-turn maintenance flow (register/edit/delete/
    # choose_vehicle) stays valid before it is discarded. Longer than the
    # shopping-list disambiguation TTL because collecting vehicle -> date -> km
    # spans several turns.
    maintenance_flow_ttl_seconds: int = 600
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

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value):
        # An empty/blank/unset LOG_LEVEL means "use the default" (INFO) rather
        # than failing validation. Any other value is normalized to uppercase
        # and checked against the standard logging levels.
        if value is None:
            return "INFO"
        if isinstance(value, str) and value.strip() == "":
            return "INFO"
        normalized = str(value).strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(
                f"log_level must be one of {sorted(allowed)}, got '{value}'"
            )
        return normalized

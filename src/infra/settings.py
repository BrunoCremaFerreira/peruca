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
    # Max history messages injected into the only-talk prompt. Bounds the prompt
    # so a long conversation cannot fill num_ctx and truncate the answer. <=0
    # keeps the full history.
    llm_only_talk_history_max_messages: int = 30

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

    # Vision model for the receipt gate+extraction call only. Empty means "use
    # the maintenance graph model"; set it to point just this call at a model
    # with better OCR (e.g. gemma4:27b) without touching code (plan §3.6).
    llm_vehicle_maintenance_vision_model: str = ""

    # Pet health classifier: near-deterministic like the other classifier graphs.
    llm_pet_health_graph_chat_model: str = "gemma4:12b"
    llm_pet_health_graph_chat_temperature: float = 0.1
    llm_pet_health_graph_chat_reasoning: bool | None = None

    # Calculator transcriber: near-deterministic like the other classifier
    # graphs — the LLM only transcribes the dictated expression, never computes.
    llm_calculator_graph_chat_model: str = "gemma4:12b"
    llm_calculator_graph_chat_temperature: float = 0.1
    llm_calculator_graph_chat_reasoning: bool | None = None

    # User settings classifier: near-deterministic like the other classifier
    # graphs — the LLM only transcribes the spoken location and, when it is sure,
    # suggests an IANA identifier; timezone_resolver decides.
    llm_user_settings_graph_chat_model: str = "gemma4:12b"
    llm_user_settings_graph_chat_temperature: float = 0.1
    llm_user_settings_graph_chat_reasoning: bool | None = None

    # Context summarizer (chat context compaction). Same model as the other
    # graphs so it stays VRAM-resident (no swap) even though it runs in the
    # background. Temperature 0.2 favours fidelity to the transcript; 0.1 makes
    # the 12b telegraphic on long-form text, which loses context.
    llm_context_summary_graph_chat_model: str = "gemma4:12b"
    llm_context_summary_graph_chat_temperature: float = 0.2
    llm_context_summary_graph_chat_reasoning: bool | None = None

    # ===============================
    # NLP Models config
    # ===============================

    nlp_spacy_model: str = "pt_core_news_sm"

    # ===============================
    # User Preferences Defaults
    # ===============================
    # IANA timezone used for a user who never set one (no row in user_settings).
    # This is the ONLY place a timezone literal lives: it is injected into
    # UserSettingsService by the IoC and reaches the graphs through
    # LlmAppService.chat() — the domain never hardcodes a zone.
    default_timezone: str = "America/Sao_Paulo"

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
    # Chat Context Compaction Config
    # ===============================
    # Background summary of the old turns of a conversation, so a long chat
    # keeps its context instead of silently losing whatever falls out of the
    # only-talk history window.
    #
    # Calibration ("no gap"): trigger_messages (30) <= the only-talk window
    # (llm_only_talk_history_max_messages, 30), so the window never drops a
    # message the summary has not covered yet — it degrades to a safety net for
    # when compaction is disabled or failing. keep_tail_messages (16) is below
    # the trigger (there must be something left to summarize) and even, so the
    # verbatim tail always starts on a turn boundary (a human/ai pair is never
    # split). With 30/16 compaction runs roughly every 7 turns.
    chat_compaction_enabled: bool = True
    chat_compaction_trigger_messages: int = 30  # fires when history >= this
    chat_compaction_trigger_chars: int = 24_000  # secondary trigger (~6k tokens)
    chat_compaction_keep_tail_messages: int = 16  # kept verbatim (8 turns)
    # Hard cap on the stored summary; enforced once, in the graph, by truncating
    # on a whole-bullet boundary (never mid-sentence).
    chat_compaction_max_summary_chars: int = 2_500

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

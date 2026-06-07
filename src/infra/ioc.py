from application.appservices.llm_app_service import LlmAppService
from application.appservices.memory_app_service import MemoryAppService
from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.smart_home_app_service import SmartHomeAppService
from application.appservices.user_app_service import UserAppService
from application.appservices.user_memory_app_service import UserMemoryAppService
from application.graphs.main_graph import MainGraph
from application.graphs.memory_graph import MemoryGraph
from application.graphs.music_graph import MusicGraph
from application.graphs.only_talk_graph import OnlyTalkGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from application.graphs.smart_home_climate_graph import SmartHomeClimateGraph
from application.graphs.smart_home_sensors_graph import SmartHomeSensorsGraph
from application.graphs.smart_home_cameras_graph import SmartHomeCamerasGraph
from domain.interfaces.data_repository import (
    ContextRepository,
    ShoppingListRepository,
    SmartHomeAreaRepository,
    SmartHomeEntityAliasRepository,
    UserMemoryRepository,
    UserRepository,
)
from domain.interfaces.music_repository import MusicRepository
from domain.interfaces.smart_home_repository import (
    SmartHomeLightRepository,
    SmartHomeClimateRepository,
    SmartHomeSensorRepository,
    SmartHomeCameraRepository,
)
from domain.services.music_service import MusicService
from domain.services.shopping_list_service import ShoppingListService
from domain.services.smart_home_service import SmartHomeService
from domain.services.user_memory_service import UserMemoryService
from domain.services.user_service import UserService
from infra.data.external.music.music_assistant.music_assistant_music_repository import (
    MusicAssistantMusicRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import (
    HomeAssistantSmartHomeConfigurationRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import (
    HomeAssistantSmartHomeLightRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_climate_repository import (
    HomeAssistantSmartHomeClimateRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_sensor_repository import (
    HomeAssistantSmartHomeSensorRepository,
)
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_camera_repository import (
    HomeAssistantSmartHomeCameraRepository,
)
from infra.data.sqlite.context_repository_redis import RedisContextRepository
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from infra.data.sqlite.sqlite_shopping_list_repository import (
    SqliteShoppingListRepository,
)
from infra.data.sqlite.sqlite_smart_home_area_repository import (
    SqliteSmartHomeAreaRepository,
)
from infra.data.sqlite.sqlite_smart_home_entity_alias_repository import (
    SqliteSmartHomeEntityAliasRepository,
)
from infra.data.sqlite.sqlite_user_memory_repository import (
    SqliteUserMemoryRepository,
)
from infra.data.sqlite.sqlite_user_repository import SqliteUserRepository
import hashlib
import os

from infra.settings import Settings

_real_settings = None
_settings_cls = None
_settings_env_snapshot = None
_repo_cache: dict = {}


def _env_snapshot() -> str:
    return hashlib.md5(str(sorted(os.environ.items())).encode()).hexdigest()


def _get_settings() -> Settings:
    global _real_settings, _settings_cls, _settings_env_snapshot
    current_snapshot = _env_snapshot()
    if _settings_cls is not Settings or _settings_env_snapshot != current_snapshot:
        _real_settings = Settings()
        _settings_cls = Settings
        _settings_env_snapshot = current_snapshot
        _repo_cache.clear()
    return _real_settings


def __getattr__(name: str):
    if name == "_settings":
        return _get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ====================================
# Graphs
# ====================================
def get_main_graph() -> MainGraph:
    """
    IOC for Main Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "main")
    if cache_key not in _repo_cache:
        # Instancing LLM Provider
        llm_chat = get_llm_chat(
            model=settings.llm_main_graph_chat_model,
            temperature=settings.llm_main_graph_chat_temperature,
        )

        only_talk_graph = get_only_talk_graph()
        shopping_list_graph = get_shopping_list_graph()
        smart_home_lights_graph = get_smart_home_lights_graph()
        smart_home_climate_graph = get_smart_home_climate_graph()
        smart_home_sensors_graph = get_smart_home_sensors_graph()
        smart_home_cameras_graph = get_smart_home_cameras_graph()
        music_graph = get_music_graph()

        _repo_cache[cache_key] = MainGraph(
            llm_chat=llm_chat,
            only_talk_graph=only_talk_graph,
            shopping_list_graph=shopping_list_graph,
            smart_home_lights_graph=smart_home_lights_graph,
            smart_home_climate_graph=smart_home_climate_graph,
            smart_home_sensors_graph=smart_home_sensors_graph,
            smart_home_cameras_graph=smart_home_cameras_graph,
            music_graph=music_graph,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_memory_graph() -> MemoryGraph:
    """
    IOC for Memory Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "memory")
    if cache_key not in _repo_cache:
        llm_chat = get_llm_chat(
            model=settings.llm_memory_graph_chat_model,
            temperature=settings.llm_memory_graph_chat_temperature,
        )

        _repo_cache[cache_key] = MemoryGraph(
            llm_chat=llm_chat, provider=settings.llm_provider_type
        )
    return _repo_cache[cache_key]


def get_only_talk_graph() -> OnlyTalkGraph:
    """
    IOC for Only Talk Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "only_talk")
    if cache_key not in _repo_cache:
        # Instancing LLM Provider
        llm_chat = get_llm_chat(
            model=settings.llm_only_talk_graph_chat_model,
            temperature=settings.llm_only_talk_graph_chat_temperature,
        )

        _repo_cache[cache_key] = OnlyTalkGraph(
            llm_chat=llm_chat, provider=settings.llm_provider_type
        )
    return _repo_cache[cache_key]


def get_shopping_list_graph() -> ShoppingListGraph:
    """
    IOC for Shopping List Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "shopping_list")
    if cache_key not in _repo_cache:
        # Instancing LLM Provider
        llm_chat = get_llm_chat(
            model=settings.llm_shopping_list_graph_chat_model,
            temperature=settings.llm_shopping_list_graph_chat_temperature,
        )

        shopping_list_service = get_shopping_list_service()

        _repo_cache[cache_key] = ShoppingListGraph(
            llm_chat=llm_chat,
            shopping_list_service=shopping_list_service,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_smart_home_lights_graph() -> SmartHomeLightsGraph:
    """
    IOC for Smart Home Lights Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "smart_home_lights")
    if cache_key not in _repo_cache:
        # Instancing LLM Provider
        llm_chat = get_llm_chat(
            model=settings.llm_smart_home_lights_graph_chat_model,
            temperature=settings.llm_smart_home_lights_graph_chat_temperature,
        )

        smart_home_service = get_smart_home_service()
        smart_home_entity_alias_repository = get_smart_home_entity_alias_repository()
        smart_home_area_repository = get_smart_home_area_repository()

        _repo_cache[cache_key] = SmartHomeLightsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=smart_home_entity_alias_repository,
            smart_home_area_repository=smart_home_area_repository,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_smart_home_climate_graph() -> SmartHomeClimateGraph:
    """
    IOC for Smart Home Climate Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "smart_home_climate")
    if cache_key not in _repo_cache:
        llm_chat = get_llm_chat(
            model=settings.llm_smart_home_climate_graph_chat_model,
            temperature=settings.llm_smart_home_climate_graph_chat_temperature,
        )

        smart_home_service = get_smart_home_service()
        smart_home_entity_alias_repository = get_smart_home_entity_alias_repository()

        _repo_cache[cache_key] = SmartHomeClimateGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=smart_home_entity_alias_repository,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_smart_home_sensors_graph() -> SmartHomeSensorsGraph:
    """
    IOC for Smart Home Sensors Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "smart_home_sensors")
    if cache_key not in _repo_cache:
        llm_chat = get_llm_chat(
            model=settings.llm_smart_home_sensors_graph_chat_model,
            temperature=settings.llm_smart_home_sensors_graph_chat_temperature,
        )

        smart_home_service = get_smart_home_service()
        smart_home_entity_alias_repository = get_smart_home_entity_alias_repository()

        _repo_cache[cache_key] = SmartHomeSensorsGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=smart_home_entity_alias_repository,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_smart_home_cameras_graph() -> SmartHomeCamerasGraph:
    """
    IOC for Smart Home Cameras Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "smart_home_cameras")
    if cache_key not in _repo_cache:
        llm_chat = get_llm_chat(
            model=settings.llm_smart_home_cameras_graph_chat_model,
            temperature=settings.llm_smart_home_cameras_graph_chat_temperature,
        )

        smart_home_service = get_smart_home_service()
        smart_home_entity_alias_repository = get_smart_home_entity_alias_repository()

        _repo_cache[cache_key] = SmartHomeCamerasGraph(
            llm_chat=llm_chat,
            smart_home_service=smart_home_service,
            smart_home_entity_alias_repository=smart_home_entity_alias_repository,
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


def get_music_graph() -> MusicGraph:
    """
    IOC for Music Graph
    """

    settings = _get_settings()

    cache_key = ("graph", "music")
    if cache_key not in _repo_cache:
        llm_chat = get_llm_chat(
            model=settings.llm_music_graph_chat_model,
            temperature=settings.llm_music_graph_chat_temperature,
        )

        _repo_cache[cache_key] = MusicGraph(
            llm_chat=llm_chat,
            music_service=get_music_service(),
            provider=settings.llm_provider_type,
        )
    return _repo_cache[cache_key]


# ====================================
# App Services
# ====================================
def get_llm_app_service() -> LlmAppService:
    """
    IOC for LLMAppService class
    """

    # Instancing
    return LlmAppService(
        main_graph=get_main_graph(),
        context_repository=get_context_repository(),
        user_repository=get_user_repository(),
        user_memory_service=get_user_memory_service(),
        music_service=get_music_service(),
    )


def get_memory_app_service() -> MemoryAppService:
    """
    IOC for MemoryAppService class
    """

    return MemoryAppService(
        memory_graph=get_memory_graph(),
        user_repository=get_user_repository(),
        user_memory_repository_factory=get_user_memory_repository,
    )


def get_user_memory_app_service() -> UserMemoryAppService:
    """
    IOC for UserMemoryAppService class
    """

    return UserMemoryAppService(user_memory_service=get_user_memory_service())


def get_user_app_service() -> UserAppService:
    """
    IOC for UserAppService class
    """

    # Instancing
    return UserAppService(
        user_service=get_user_service(), user_repository=get_user_repository()
    )


def get_shopping_list_app_service() -> ShoppingListAppService:
    """
    IOC for ShoppingListAppService class
    """

    return ShoppingListAppService(
        shopping_list_repository=get_shopping_list_repository(),
        shopping_list_service=get_shopping_list_service(),
    )


def get_smart_home_app_service() -> SmartHomeAppService:
    """
    IOC for SmartHomeAppService
    """

    return SmartHomeAppService(
        smart_home_light_repository=get_smart_home_light_repository(),
        smart_home_entity_alias_repository=get_smart_home_entity_alias_repository(),
        smart_home_service=get_smart_home_service(),
    )


# ====================================
# Domain Services
# ====================================


def get_music_repository() -> MusicRepository:
    """
    IOC for Music Repository
    """

    settings = _get_settings()
    cache_key = ("music", settings.music_assistant_url, settings.music_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = MusicAssistantMusicRepository(
            base_url=settings.music_assistant_url,
            token=settings.music_assistant_token,
        )
    return _repo_cache[cache_key]


def get_music_service() -> MusicService:
    """
    IOC for Music Service
    """

    _get_settings()
    cache_key = ("service", "music")
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = MusicService(
            music_repository=get_music_repository(),
        )
    return _repo_cache[cache_key]


def get_user_service() -> UserService:
    """
    IOC for User Service
    """

    return UserService(user_repository=get_user_repository())


def get_user_memory_service() -> UserMemoryService:
    """
    IOC for User Memory Service
    """

    return UserMemoryService(
        user_memory_repository=get_user_memory_repository()
    )


def get_shopping_list_service() -> ShoppingListRepository:
    """
    IOC for Shopping List Service
    """

    return ShoppingListService(shopping_list_repository=get_shopping_list_repository())


def get_smart_home_service() -> SmartHomeService:
    """
    IOC for Smart Home Service
    """

    return SmartHomeService(
        smart_home_entity_alias_repository=get_smart_home_entity_alias_repository(),
        smart_home_configuration_repository=get_home_assistant_smart_home_configuration_repository(),
        smart_home_light_repository=get_smart_home_light_repository(),
        smart_home_climate_repository=get_smart_home_climate_repository(),
        smart_home_sensor_repository=get_smart_home_sensor_repository(),
        smart_home_camera_repository=get_smart_home_camera_repository(),
        smart_home_area_repository=get_smart_home_area_repository(),
    )


# ====================================
# Data Repositories
# ====================================


def get_context_repository() -> ContextRepository:
    """
    IOC for Cache Repository
    """

    settings = _get_settings()
    connection_string = settings.cache_db_connection_string

    return RedisContextRepository(connection_string)


def get_user_repository() -> UserRepository:
    """
    User Repository
    """

    settings = _get_settings()
    cache_key = ("sqlite_user", settings.peruca_db_connection_string)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = SqliteUserRepository(db_path=settings.peruca_db_connection_string)
    return _repo_cache[cache_key]


def get_user_memory_repository() -> UserMemoryRepository:
    """
    User Memory Repository
    """

    settings = _get_settings()
    cache_key = ("sqlite_user_memory", settings.peruca_db_connection_string)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = SqliteUserMemoryRepository(db_path=settings.peruca_db_connection_string)
    return _repo_cache[cache_key]


def get_shopping_list_repository() -> ShoppingListRepository:
    """
    Shopping List Repository
    """

    settings = _get_settings()
    cache_key = ("sqlite_shopping_list", settings.peruca_db_connection_string)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = SqliteShoppingListRepository(db_path=settings.peruca_db_connection_string)
    return _repo_cache[cache_key]


def get_smart_home_entity_alias_repository() -> SmartHomeEntityAliasRepository:
    """
    Smart Home Entity Alias Repository
    """
    settings = _get_settings()
    cache_key = ("sqlite_entity_alias", settings.peruca_db_connection_string)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = SqliteSmartHomeEntityAliasRepository(
            db_path=settings.peruca_db_connection_string
        )
    return _repo_cache[cache_key]


def get_smart_home_area_repository() -> SmartHomeAreaRepository:
    """
    Smart Home Area Repository
    """
    settings = _get_settings()
    cache_key = ("sqlite_area", settings.peruca_db_connection_string)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = SqliteSmartHomeAreaRepository(db_path=settings.peruca_db_connection_string)
    return _repo_cache[cache_key]


# ====================================
# Smart Home Repositories
# ====================================
def get_smart_home_light_repository() -> SmartHomeLightRepository:
    """
    Smart Home Light Repository
    """

    settings = _get_settings()
    cache_key = ("light", settings.home_assistant_url, settings.home_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = HomeAssistantSmartHomeLightRepository(
            base_url=settings.home_assistant_url, token=settings.home_assistant_token
        )
    return _repo_cache[cache_key]


def get_smart_home_climate_repository() -> SmartHomeClimateRepository:
    """
    Smart Home Climate Repository
    """

    settings = _get_settings()
    cache_key = ("climate", settings.home_assistant_url, settings.home_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = HomeAssistantSmartHomeClimateRepository(
            base_url=settings.home_assistant_url, token=settings.home_assistant_token
        )
    return _repo_cache[cache_key]


def get_smart_home_sensor_repository() -> SmartHomeSensorRepository:
    """
    Smart Home Sensor Repository
    """

    settings = _get_settings()
    cache_key = ("sensor", settings.home_assistant_url, settings.home_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = HomeAssistantSmartHomeSensorRepository(
            base_url=settings.home_assistant_url, token=settings.home_assistant_token
        )
    return _repo_cache[cache_key]


def get_smart_home_camera_repository() -> SmartHomeCameraRepository:
    """
    Smart Home Camera Repository
    """

    settings = _get_settings()
    cache_key = ("camera", settings.home_assistant_url, settings.home_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = HomeAssistantSmartHomeCameraRepository(
            base_url=settings.home_assistant_url, token=settings.home_assistant_token
        )
    return _repo_cache[cache_key]


def get_home_assistant_smart_home_configuration_repository() -> (
    HomeAssistantSmartHomeConfigurationRepository
):
    """
    Smart Configurations Repository
    """

    settings = _get_settings()
    cache_key = ("ha_config", settings.home_assistant_url, settings.home_assistant_token)
    if cache_key not in _repo_cache:
        _repo_cache[cache_key] = HomeAssistantSmartHomeConfigurationRepository(
            websocket_url=settings.home_assistant_url, token=settings.home_assistant_token
        )
    return _repo_cache[cache_key]


# ====================================
# LLM Classes
# ====================================


def get_llm_chat(model: str, temperature: float) -> BaseChatModel:
    """
    Return LLM provider
    """

    settings = _get_settings()
    provider_type = settings.llm_provider_type.upper()

    if provider_type == "OPENAI":
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=settings.llm_provider_api_key,
        )
    elif provider_type == "OLLAMA":
        return ChatOllama(
            base_url=settings.llm_provider_url,
            model=model,
            temperature=temperature,
            keep_alive=settings.llm_keep_alive,
            num_ctx=settings.llm_num_ctx,
            num_predict=settings.llm_num_predict,
        )
    else:
        raise ValueError(f"Invalid provider type: {provider_type!r}")

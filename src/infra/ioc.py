from application.appservices.llm_app_service import LlmAppService
from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.smart_home_app_service import SmartHomeAppService
from application.appservices.user_app_service import UserAppService
from application.graphs.main_graph import MainGraph
from application.graphs.only_talk_graph import OnlyTalkGraph
from application.graphs.shopping_list_graph import ShoppingListGraph
from application.graphs.smart_home_lights_graph import SmartHomeLightsGraph
from domain.interfaces.data_repository import ContextRepository, ShoppingListRepository, SmartHomeEntityAliasRepository, UserRepository
from domain.interfaces.smart_home_repository import SmartHomeLightRepository
from domain.services.shopping_list_service import ShoppingListService
from domain.services.smart_home_service import SmartHomeService
from domain.services.user_service import UserService
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_configuration_repository import HomeAssistantSmartHomeConfigurationRepository
from infra.data.external.smart_home.home_assistant.home_assistant_smart_home_light_repository import HomeAssistantSmartHomeLightRepository
from infra.data.sqlite.context_repository_redis import RedisContextRepository
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from infra.data.sqlite.sqlite_shopping_list_repository import SqliteShoppingListRepository
from infra.data.sqlite.sqlite_smart_home_entity_alias_repository import SqliteSmartHomeEntityAliasRepository
from infra.data.sqlite.sqlite_user_repository import SqliteUserRepository
from infra.settings import Settings

# ====================================
# Graphs
# ====================================
def get_main_graph() -> MainGraph:
    """
    IOC for Main Graph
    """

    settings = Settings()
    
    # Instancing LLM Provider
    llm_chat = get_llm_chat(model=settings.llm_main_graph_chat_model,
            temperature=settings.llm_main_graph_chat_temperature)
    
    only_talk_graph = get_only_talk_graph()
    shopping_list_graph = get_shopping_list_graph()
    smart_home_lights_graph = get_smart_home_lights_graph()
    
    return MainGraph(llm_chat=llm_chat, 
                     only_talk_graph=only_talk_graph, 
                     shopping_list_graph=shopping_list_graph,
                     smart_home_lights_graph=smart_home_lights_graph)

def get_only_talk_graph() -> OnlyTalkGraph:
    """
    IOC for Only Talk Graph
    """

    settings = Settings()
    
    # Instancing LLM Provider
    llm_chat = get_llm_chat(model=settings.llm_only_talk_graph_chat_model,
            temperature=settings.llm_only_talk_graph_chat_temperature)
    
    return OnlyTalkGraph(llm_chat=llm_chat)

def get_shopping_list_graph() -> ShoppingListGraph:
    """
    IOC for Shopping List Graph
    """

    settings = Settings()
    
    # Instancing LLM Provider
    llm_chat = get_llm_chat(model=settings.llm_shopping_list_graph_chat_model,
            temperature=settings.llm_shopping_list_graph_chat_temperature)
    
    shopping_list_service = get_shopping_list_service()
    
    return ShoppingListGraph(llm_chat=llm_chat, shopping_list_service=shopping_list_service)

def get_smart_home_lights_graph() -> SmartHomeLightsGraph:
    """
    IOC for Smart Home Lights Graph
    """

    settings = Settings()
    
    # Instancing LLM Provider
    llm_chat = get_llm_chat(model=settings.llm_smart_home_lights_graph_chat_model,
            temperature=settings.llm_smart_home_lights_graph_chat_temperature)
    
    smart_home_service = get_smart_home_service()
    
    return SmartHomeLightsGraph(llm_chat=llm_chat, smart_home_service=smart_home_service)

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
        user_repository=get_user_repository()
    )

def get_user_app_service() -> UserAppService:
    """
    IOC for UserAppService class
    """

    # Instancing
    return UserAppService(
        user_service=get_user_service(),
        user_repository=get_user_repository()
    )

def get_shopping_list_app_service() -> ShoppingListAppService:
    """
    IOC for ShoppingListAppService class
    """

    return ShoppingListAppService(
        shopping_list_repository=get_shopping_list_repository(),
        shopping_list_service=get_shopping_list_service()
    )

def get_smart_home_app_service() -> SmartHomeAppService:
    """
    IOC for SmartHomeAppService
    """

    return SmartHomeAppService(
        smart_home_light_repository=get_smart_home_light_repository(),
        smart_home_entity_alias_repository= get_smart_home_entity_alias_repository(),
        smart_home_service=get_smart_home_service()
    )

# ====================================
# Domain Services
# ====================================
def get_user_service() -> UserService:
    """
    IOC for User Service
    """

    return UserService(user_repository=get_user_repository())

def get_shopping_list_service() -> ShoppingListRepository:
    """
    IOC for Shopping List Service
    """

    return ShoppingListService(shopping_list_repository=get_shopping_list_repository())

def get_smart_home_service() -> SmartHomeService:
    """
    IOC for Smart Home Service
    """

    return SmartHomeService(smart_home_entity_alias_repository = get_smart_home_entity_alias_repository(),
                            smart_home_configuration_repository=get_home_assistant_smart_home_configuration_repository(), 
                            smart_home_light_repository=get_smart_home_light_repository())

# ====================================
# Data Repositories
# ====================================


def get_context_repository() -> ContextRepository:
    """
    IOC for Cache Repository
    """

    settings = Settings()
    connection_string = settings.cache_db_connection_string

    return RedisContextRepository(connection_string)

def get_user_repository() -> UserRepository:
    """
    User Repository
    """

    settings = Settings()
    return SqliteUserRepository(db_path=settings.peruca_db_connection_string)

def get_shopping_list_repository() -> ShoppingListRepository:
    """
    Shopping List Repository
    """

    settings = Settings()
    return SqliteShoppingListRepository(db_path=settings.peruca_db_connection_string)

def get_smart_home_entity_alias_repository() -> SmartHomeEntityAliasRepository:
    """
    Smart Home Entity Alias Repository
    """
    settings = Settings()
    return SqliteSmartHomeEntityAliasRepository(db_path=settings.peruca_db_connection_string)

# ====================================
# Smart Home Repositories
# ====================================
def get_smart_home_light_repository() -> SmartHomeLightRepository:
    """
    Smart Home Light Repository
    """

    settings = Settings()
    return HomeAssistantSmartHomeLightRepository(base_url=settings.home_assistant_url, 
                                                 token=settings.home_assistant_token)

def get_home_assistant_smart_home_configuration_repository() -> HomeAssistantSmartHomeConfigurationRepository:
    """
    Smart Configurations Repository
    """

    settings = Settings()
    return HomeAssistantSmartHomeConfigurationRepository(websocket_url=settings.home_assistant_url,
                                                         token=settings.home_assistant_token)

# ====================================
# LLM Classes
# ====================================

def get_llm_chat(model: str, temperature: float) -> BaseChatModel:
    """
    Return LLM provider
    """
    
    settings = Settings()
    provider_type = settings.llm_provider_type.upper()

    if provider_type == "OPENAI":
        raise ValueError("Open Ai not supported yet!")
    
    elif provider_type == "OLLAMA":
        return ChatOllama(
            base_url=settings.llm_provider_url, 
            model=model,
            temperature=temperature)
    else:
        raise ValueError("Invalid provider type")
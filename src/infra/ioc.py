from application.appservices.llm_app_service import LlmAppService
from application.appservices.shopping_list_app_service import ShoppingListAppService
from application.appservices.user_app_service import UserAppService
from domain.graphs.main_graph import MainGraph
from domain.graphs.only_talk_graph import OnlyTalkGraph
from domain.interfaces.repository import ContextRepository, UserRepository
from domain.services.user_service import UserService
from infra.data.context_repository_redis import RedisContextRepository
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from infra.data.user_repository_sqlite import UserRepositorySqlite
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
    
    return MainGraph(llm_chat=llm_chat, only_talk_graph=only_talk_graph)

def get_only_talk_graph() -> OnlyTalkGraph:
    """
    IOC for Only Talk Graph
    """

    settings = Settings()
    
    # Instancing LLM Provider
    llm_chat = get_llm_chat(model=settings.llm_only_talk_graph_chat_model,
            temperature=settings.llm_only_talk_graph_chat_temperature)
    
    return OnlyTalkGraph(llm_chat=llm_chat)

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

    return ShoppingListAppService()

# ====================================
# Domain Services
# ====================================
def get_user_service() -> UserService:
    """
    IOC for User Service
    """

    return UserService(user_repository=get_user_repository())

# ====================================
# Repositories
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
    return UserRepositorySqlite(db_path= settings.peruca_db_connection_string)

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
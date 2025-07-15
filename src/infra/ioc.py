from application.appservices.llm_app_service import LlmAppService
from domain.graphs.main_graph import MainGraph
from domain.interfaces.repository import ContextRepository
from infra.data.context_repository_redis import RedisContextRepository
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
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
    return MainGraph(llm_chat)

# ====================================
# App Services
# ====================================
def get_llm_app_service() -> LlmAppService:
    """
    IOC for LLMAppService class
    """

    # Instancing Cache Database
    context_repository = get_context_repository()

    # Instancing
    return LlmAppService(
        context_repository=context_repository, 
        main_graph=get_main_graph()
    )

# ====================================
# Domain Services
# ====================================



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
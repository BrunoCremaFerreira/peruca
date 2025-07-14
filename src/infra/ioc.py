from application.appservices.llm_app_service import LlmAppService
from domain.graphs.main_graph import MainGraph
from domain.interfaces.repository import ContextRepository
from infra.data.context_repository_redis import RedisContextRepository
from langchain_community.chat_models import ChatOllama
from infra.settings import Settings

# ====================================
# App Services
# ====================================


def get_llm_app_service() -> LlmAppService:
    """
    IOC for LLMAppService class
    """
    settings = Settings()

    provider_type = settings.llm_provider_type.upper()

    # Instancing LLM Provider
    if provider_type == "OPENAI":
        raise ValueError("Open Ai not supported yet!")
    elif provider_type == "OLLAMA":
        llm_chat=ChatOllama(
            base_url=settings.llm_provider_url, 
            model=settings.llm_main_graph_chat_model,
            temperature=0.5)
    else:
        raise ValueError("Invalid provider type")

    # Instancing Cache Database
    context_repository = get_context_repository()

    # Instancing
    return LlmAppService(
        context_repository=context_repository, 
        llm_chat=llm_chat,
        main_graph=MainGraph()
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

from application.appservices.llm_app_service import LlmAppService
from domain.interfaces.repository import ContextRepository
from domain.services.llm_service import LlmService
from infra.data.context_repository_redis import RedisContextRepository
from infra.data.llm_repository_gemini import GeminiLlmRepository
from infra.data.llm_repository_llama3 import Llama3LlmRepository
from infra.data.llm_repository_open_ai import OpenAiLlmRepository
from infra.settings import Settings

# ====================================
# App Services
# ====================================


def get_llm_app_service() -> LlmAppService:
    """
    IOC for LLM App Service
    """
    return LlmAppService(get_llm_service())


# ====================================
# Domain Services
# ====================================


def get_llm_service() -> LlmService:
    """
    IOC for LLM Service
    """
    settings = Settings()

    api_key = settings.llm_provider_api_key
    provider_type = settings.llm_provider_type

    # Instancing LLM Provider
    if provider_type == "openai":
        llm_repository = OpenAiLlmRepository(api_key)
    elif provider_type == "gemini":
        llm_repository = GeminiLlmRepository(api_key)
    elif provider_type == "llama":
        llm_repository = Llama3LlmRepository()
    else:
        raise ValueError("Invalid provider type")

    # Instancing Cache Database
    context_repository = get_context_repository()

    # Instancing
    return LlmService(
        llm_repository=llm_repository, context_repository=context_repository
    )


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

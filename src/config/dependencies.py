from adapters.outbound.cache.redis_cache import RedisCache
from adapters.outbound.llm_providers.openai_provider import OpenAIProvider
from adapters.outbound.llm_providers.gemini_provider import GeminiProvider
from adapters.outbound.llm_providers.llama_provider import LLaMAProvider
from config.settings import Settings
from domain.ports.outbound.cache_outbound_port import CacheOutboundPort
from domain.services.llm_service import LLMService
from application.use_cases.chat_use_case import ChatUseCase


def get_llm_service():
    """
    IOC for LLMOutboundPort interface
    """
    settings = Settings()

    api_key = settings.llm_provider_api_key
    provider_type = settings.llm_provider_type

    # Instancing LLM Provider
    if provider_type == "openai":
        provider = OpenAIProvider(api_key)
    elif provider_type == "gemini":
        provider = GeminiProvider(api_key)
    elif provider_type == "llama":
        provider = LLaMAProvider()
    else:
        raise ValueError("Invalid provider type")

    # Instancing Cache Database
    cache_database = get_cache_database()

    # Instancing
    return LLMService(provider, cache_database)


def get_cache_database() -> CacheOutboundPort:
    """
    IOC for cache database
    """
    settings = Settings()
    connection_string = settings.cache_db_connection_string

    return RedisCache(connection_string)


def get_chat_response_use_case():
    llm_service = get_llm_service()
    return ChatUseCase(llm_service)

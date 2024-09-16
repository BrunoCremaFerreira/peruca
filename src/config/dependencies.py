import os
from adapters.outbound.providers.openai_provider import OpenAIProvider
from adapters.outbound.providers.gemini_provider import GeminiProvider
from adapters.outbound.providers.llama_provider import LLaMAProvider
from domain.services.llm_service import LLMService
from application.use_cases.generate_response_use_case import GenerateResponseUseCase


def get_llm_service():
    provider_type = os.getenv("PROVIDER_TYPE", "openai")
    api_key = os.getenv("API_KEY")

    provider_map = {
        "openai": lambda: OpenAIProvider(api_key),
        "gemini": lambda: GeminiProvider(api_key),
        "llama": lambda: LLaMAProvider(),
    }

    try:
        provider = provider_map[provider_type]()
    except KeyError:
        raise ValueError("Invalid provider type")

    return LLMService(provider)


def get_generate_response_use_case():
    llm_service = get_llm_service()
    return GenerateResponseUseCase(llm_service)

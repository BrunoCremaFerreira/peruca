from adapters.outbound.providers.openai_provider import OpenAIProvider
from adapters.outbound.providers.gemini_provider import GeminiProvider
from adapters.outbound.providers.llama_provider import LLaMAProvider
from domain.services.llm_service import LLMService
from application.use_cases.generate_response_use_case import GenerateResponseUseCase

def get_llm_service():
    provider_type = "openai"  # Setting OpenAi
    if provider_type == "openai":
        provider = OpenAIProvider(api_key="YOUR_OPENAI_API_KEY")
    elif provider_type == "gemini":
        provider = GeminiProvider(api_key="YOUR_GOOGLE_GEMINI_API_KEY")
    elif provider_type == "llama":
        provider = LLaMAProvider()
    else:
        raise ValueError("Invalid provider type")
    
    return LLMService(provider)

def get_generate_response_use_case():
    llm_service = get_llm_service()
    return GenerateResponseUseCase(llm_service)

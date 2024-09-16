import os


class Settings:
    """
    Application Environment Config
    """

    def __init__(self) -> None:
        self.llm_provider = LLMProviderSettings()
        self.cache_database = CacheDatabaseSettings()


class LLMProviderSettings:
    """
    LLM Provider Settings
    """

    def __init__(self) -> None:
        self.type = os.getenv("PROVIDER_TYPE", "openai")
        self.api_key = os.getenv("API_KEY", "")


class CacheDatabaseSettings:
    """
    Cache Database Settings
    """

    def __init__(self) -> None:
        self.connection_string = os.getenv("CACHE_DB_CONNECTION_STRING", "")

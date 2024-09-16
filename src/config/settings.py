import os

from domain.exceptions import InvalidEnvironmentSettingsError


class Settings:
    """
    Application Environment Config
    """

    def __init__(self) -> None:
        self.llm_provider = LLMProviderSettings()
        self.cache_database = CacheDatabaseSettings()

    def validate(self) -> None:
        """
        Validate all required settings
        """

        self.llm_provider.validate()
        self.cache_database.validate()


class LLMProviderSettings:
    """
    LLM Provider Settings
    """

    def __init__(self) -> None:
        self.type = os.getenv("PROVIDER_TYPE", "openai").strip()
        self.api_key = os.getenv("API_KEY", "").strip()

    def validate(self) -> None:
        """
        Validate all required settings
        """

        if self.type == "":
            raise InvalidEnvironmentSettingsError(
                "Env Param PROVIDER_TYPE, is required"
            )

        if self.api_key == "" and self.type != "llama":
            raise InvalidEnvironmentSettingsError("Env Param API_KEY, is required")


class CacheDatabaseSettings:
    """
    Cache Database Settings
    """

    def __init__(self) -> None:
        self.connection_string = os.getenv("CACHE_DB_CONNECTION_STRING", "")

    def validate(self) -> None:
        """
        Validate all required settings
        """

        if self.connection_string == "":
            raise InvalidEnvironmentSettingsError(
                "Env Param CACHE_DB_CONNECTION_STRING, is required"
            )

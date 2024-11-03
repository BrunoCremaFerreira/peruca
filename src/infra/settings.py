from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Environment Config
    """

    llm_provider_type: str = "openai"
    llm_provider_api_key: str = ""
    cache_db_connection_string: str = ""

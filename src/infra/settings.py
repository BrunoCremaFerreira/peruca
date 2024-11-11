from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Environment Config
    """

    # ===============================
    # LLM Provider Configs
    # ===============================

    llm_provider_type: str = "openai"
    llm_provider_api_key: str = ""

    # ===============================
    # Databases Config
    # ===============================

    cache_db_connection_string: str = ""
    peruca_db_connection_string: str = (
        "postgresql://username:password@localhost:5432/peruca"
    )

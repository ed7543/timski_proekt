from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
GROQ_API_KEY = settings.GROQ_API_KEY
TAVILY_API_KEY = settings.TAVILY_API_KEY
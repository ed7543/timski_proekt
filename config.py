from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    DATABASE_URL: str = ""
    JWT_SECRET_KEY: str = ""
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8000"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "LearnWise <onboarding@resend.dev>"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
GROQ_API_KEY = settings.GROQ_API_KEY
TAVILY_API_KEY = settings.TAVILY_API_KEY
DATABASE_URL = settings.DATABASE_URL
JWT_SECRET_KEY = settings.JWT_SECRET_KEY
ALLOWED_ORIGINS = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
RESEND_API_KEY = settings.RESEND_API_KEY
EMAIL_FROM = settings.EMAIL_FROM
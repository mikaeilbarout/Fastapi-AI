from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str
    openai_api_key: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    admin_email: str
    GLOBAL_RATE_LIMIT: int
    AUTH_RATE_LIMIT: int
    TIME_WINDOW_SECONDS: int
    redis_url: str
    database_url: str
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
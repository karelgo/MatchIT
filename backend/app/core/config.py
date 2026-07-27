from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MATCHIT_", extra="ignore")

    app_name: str = "MatchIT"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://matchit:matchit@localhost:5432/matchit"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    apple_client_id: str = "com.matchit.app"
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    apple_issuer: str = "https://appleid.apple.com"

    llm_provider: str = "anthropic"  # anthropic | openai | fake
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    embedding_provider: str = "openai"  # openai | fake
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    pubsub_backend: str = "redis"  # redis | memory
    vector_backend: str = "qdrant"  # qdrant | memory
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

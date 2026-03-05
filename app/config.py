from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    FRONTEND_URL: str = "https://www.deepflytechlabs.com"

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 6
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ADMIN_PASSWORD: str

    # LLM providers — at least one must be configured
    ANTHROPIC_API_KEY: str = ""
    NVIDIA_API_KEY: str = "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"

    # Email
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "hello@deepflytechlabs.com"

    # Agent schedules
    RESEARCH_AGENT_CRON: str = "0 8 * * 1"
    JOBS_AGENT_CRON: str = "0 6 * * *"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "test"

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def allowed_origins(self) -> list[str]:
        base = [self.FRONTEND_URL, "http://localhost:5173"]
        if not self.is_production:
            base += ["http://localhost:3000", "http://127.0.0.1:5173"]
        return base

    @property
    def has_llm(self) -> bool:
        """True if at least one LLM provider is configured."""
        return bool(self.ANTHROPIC_API_KEY or self.NVIDIA_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore


settings = get_settings()
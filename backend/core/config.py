from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # the same variables the postgres container is configured with, so the credentials
    # are written once and DATABASE_URL is derived rather than duplicated
    POSTGRES_USER: str = "geotriage"
    POSTGRES_PASSWORD: str = "geotriage"
    POSTGRES_DB: str = "geotriage"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # set this to point somewhere the parts above can't express, e.g. a managed instance
    # with its own sslmode
    DATABASE_URL_OVERRIDE: str | None = None

    MINIO_ENDPOINT: str
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_BUCKET: str

    LLM_BASE_URL: str = "http://ollama:11434"
    LLM_MODEL: str = "qwen3:4b-instruct-2507-q4_K_M"
    LLM_TIMEOUT_SECONDS: float = 300.0
    LLM_CONTEXT_TOKENS: int = 8192

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()

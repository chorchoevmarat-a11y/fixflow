from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every value can be overridden by an environment variable."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://fixflow:fixflow@localhost:5432/fixflow"
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000"
    UPLOAD_DIR: str = "./uploads"

    SESSION_TTL_MINUTES: int = 12 * 60
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_FAILURE_WINDOW_MINUTES: int = 15

    MAX_JSON_BODY_BYTES: int = 1024 * 1024
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    MAX_IMAGE_PIXELS: int = 40_000_000
    MAX_IMAGE_SIDE: int = 10_000
    MAX_INTAKE_IMAGES: int = 3

    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in {"development", "dev", "test", "local"}


settings = Settings()

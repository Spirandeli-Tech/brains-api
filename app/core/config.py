from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""
    CORS_ORIGINS: str = "http://localhost:5173"
    ENCRYPTION_KEY: str = ""
    # Shared secret the host-side implementation runner presents (X-Runner-Token)
    # to claim runs and patch status. Empty disables the runner endpoints.
    RUNNER_TOKEN: str = ""
    # Read-only mount of the host's ~/.claude, used to discover available skills for automations.
    CLAUDE_HOME_DIR: str = "/root/.claude"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields like POSTGRES_USER, POSTGRES_PASSWORD, etc.

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


settings = Settings()

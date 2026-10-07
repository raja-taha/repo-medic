from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "RepoMedic"
    log_level: str = "INFO"
    secret_key: str = "change-me"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    database_url: str = (
        "postgresql+asyncpg://repomedic:repomedic_dev_password@localhost:5433/repomedic"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://repomedic:repomedic_dev_password@localhost:5433/repomedic"
    )

    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "repomedic-tasks"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    github_token: str = ""
    github_webhook_secret: str = ""

    sandbox_enabled: bool = True
    sandbox_image: str = "repomedic-sandbox:latest"
    sandbox_memory_limit: str = "1g"
    sandbox_cpu_limit: float = 1.0
    sandbox_timeout_seconds: int = 120
    sandbox_network_disabled: bool = True
    workspace_root: Path = Field(default=Path("./workspaces"))

    max_patch_attempts: int = 3
    max_files_changed: int = 15
    max_diff_bytes: int = 200_000
    agent_step_timeout_seconds: int = 300

    allow_auto_pr: bool = False
    synthetic_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
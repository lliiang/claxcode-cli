"""Global configuration for ClaxCode."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings."""

    # App
    app_name: str = "ClaxCode"
    debug: bool = Field(default=False, validation_alias="CLAXCODE_DEBUG")

    # LLM
    llm_provider: str = "openai"  # openai | anthropic | generic_openai
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096
    llm_custom_config: str = ""  # JSON string for custom provider settings

    # Context
    max_context_tokens: int = 128000
    context_compression_threshold: float = 0.85

    # Storage
    database_url: str = "sqlite+aiosqlite:///./.claxcode/claxcode.db"
    snapshots_dir: Path = Path("./.claxcode/snapshots")
    project_context_file: str = "CLAUDE.md"

    # Security
    permission_mode: str = "ask"  # ask | auto_edit | plan | auto_safe | yolo

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Tool Execution
    tool_timeout: int = 60  # seconds

    # Browser
    browser_headless: bool = True  # headless mode for Playwright browser tools

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

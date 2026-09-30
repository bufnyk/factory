from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gh_secret: SecretStr
    github_token: SecretStr
    claude_setup_token: SecretStr
    claude_model: str = "claude-opus-5-5"
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    codex_model: str = "gpt-6-sol"
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    codex_auth_path: Path = Path.home() / ".codex" / "auth.json"
    loop_limit: int = Field(ge=2, le=8, multiple_of=2, default=4)


@lru_cache
def get_settings() -> Settings:
    return Settings()

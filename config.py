from pydantic_settings import BaseSettings, SettingsConfigDict, 
from pydantic import Field, SecretStr
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    gh_secret: SecretStr

@lru_cache
def get_settings() -> Settings:
    return Settings()

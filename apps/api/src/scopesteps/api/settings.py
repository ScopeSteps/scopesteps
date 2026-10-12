from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from scopesteps.api.modules import MODULE_NAMES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "demo", "production"] = "local"
    database_url: str = "postgresql+psycopg://scopesteps:scopesteps@127.0.0.1:5432/scopesteps"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    enabled_modules: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(MODULE_NAMES)
    )

    @field_validator("cors_allowed_origins", "enabled_modules", mode="before")
    @classmethod
    def split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("enabled_modules")
    @classmethod
    def reject_unknown_modules(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(MODULE_NAMES))
        if unknown:
            raise ValueError(f"Unknown modules in ENABLED_MODULES: {', '.join(unknown)}")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

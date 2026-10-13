from decimal import Decimal
from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from scopesteps.api.modules import MODULE_NAMES

LOCAL_ENVIRONMENTS = frozenset({"local", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore", frozen=True
    )

    app_env: Literal["local", "test", "demo", "production"] = "local"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite:///var/scopesteps.db"
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    enabled_modules: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(MODULE_NAMES)
    )
    auth_mode: Literal["local"] = "local"

    model_provider: Literal["none", "gemini"] = "none"
    model_id: str | None = None
    model_api_key: SecretStr | None = None
    # ADR 0004: gemini-3.5-flash-lite answered typed drafts in under 9 s during the probe.
    model_timeout_seconds: float = Field(default=30, gt=0, le=300)
    model_thinking_level: Literal["minimal", "low", "medium", "high"] = "minimal"

    run_max_turns: int = Field(default=6, ge=1)
    run_max_tools: int = Field(default=8, ge=1)
    run_max_clarification_rounds: int = Field(default=2, ge=0)
    run_max_output_tokens: int = Field(default=8000, ge=1)
    # Input + output + thinking tokens across the whole run, checked before every model call.
    run_max_total_tokens: int = Field(default=200_000, ge=1)
    run_cost_limit_usd: Decimal | None = Field(default=None, gt=0)
    # How long one advance may hold a run. It must outlast a draft and its repair (two calls), or
    # another request could take the run over while the step is still running.
    run_lease_seconds: float = Field(default=90, gt=0)
    project_cost_limit_usd: Decimal | None = Field(default=None, gt=0)
    source_max_bytes: int = Field(default=512 * 1024, ge=1)
    source_max_words: int = Field(default=6000, ge=1)

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

    @model_validator(mode="after")
    def check_local_auth_is_local_only(self) -> Self:
        if self.auth_mode == "local" and (
            self.app_env not in LOCAL_ENVIRONMENTS or not _is_loopback_host(self.api_host)
        ):
            raise ValueError(
                "AUTH_MODE=local requires APP_ENV=local or test and a loopback API_HOST"
            )
        return self

    @model_validator(mode="after")
    def check_lease_outlasts_a_step(self) -> Self:
        if self.run_lease_seconds < 2 * self.model_timeout_seconds:
            raise ValueError("RUN_LEASE_SECONDS must be at least twice MODEL_TIMEOUT_SECONDS")
        return self

    @model_validator(mode="after")
    def check_model_provider_is_configured(self) -> Self:
        if self.model_provider != "none" and (self.model_id is None or self.model_api_key is None):
            raise ValueError(
                f"MODEL_PROVIDER={self.model_provider} requires MODEL_ID and MODEL_API_KEY"
            )
        return self


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()

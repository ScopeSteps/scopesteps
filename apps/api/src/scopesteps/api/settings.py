from decimal import Decimal
from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from scopesteps.agent.client import PROFILES, ModelConfig, ProviderName
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
    # local: every request acts as the seeded reviewer. session: password sign-in and a session
    # cookie. Which one is the default, and when that changes, is decided in ADR 0007.
    auth_mode: Literal["local", "session"] = "local"
    session_absolute_lifetime_minutes: int = Field(default=12 * 60, ge=5, le=7 * 24 * 60)
    session_idle_timeout_minutes: int = Field(default=2 * 60, ge=1)
    # The password `just seed` gives the synthetic accounts. Unset by default: no password is
    # committed, and the seed then leaves those accounts unable to sign in. Its length is checked
    # by the seed, not here: a settings validation error would quote the value.
    seed_account_password: SecretStr | None = None

    # The one provider this process uses. Switching is a deliberate edit, never automatic: a silent
    # fallback would mix models in results and send data where nobody chose (ADR 0004, ADR 0006).
    model_provider: Literal["none", "gemini", "groq"] = "none"
    # Opt-in backup for product runs only: a run that has not had one successful call moves to it
    # when the primary is overloaded, timing out or rate limited. Probes and evaluations never
    # fall back; they pin one model.
    model_fallback_provider: Literal["none", "gemini", "groq"] = "none"
    gemini_api_key: SecretStr | None = None
    gemini_model_id: str = PROFILES["gemini"].default_model
    # Defaults come from each provider's profile (modules/agent/.../providers/<name>.py), where its
    # limits are recorded with the date they were checked.
    groq_api_key: SecretStr | None = None
    groq_model_id: str = PROFILES["groq"].default_model
    groq_base_url: str = PROFILES["groq"].base_url or ""
    groq_tokens_per_minute: int | None = Field(
        default=PROFILES["groq"].free_tier.tokens_per_minute, ge=1
    )
    groq_max_output_tokens: int | None = Field(default=PROFILES["groq"].max_output_tokens_cap, ge=1)
    # A ceiling, not expected latency: a slower call fails as a timeout, never retried (ADR 0004).
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
            not self.is_local_environment or not _is_loopback_host(self.api_host)
        ):
            raise ValueError(
                "AUTH_MODE=local requires APP_ENV=local or test and a loopback API_HOST"
            )
        return self

    @model_validator(mode="after")
    def check_idle_timeout_fits_the_session_lifetime(self) -> Self:
        if self.session_idle_timeout_minutes > self.session_absolute_lifetime_minutes:
            raise ValueError(
                "SESSION_IDLE_TIMEOUT_MINUTES must not exceed SESSION_ABSOLUTE_LIFETIME_MINUTES"
            )
        return self

    @model_validator(mode="after")
    def check_lease_outlasts_a_step(self) -> Self:
        if self.run_lease_seconds < 2 * self.model_timeout_seconds:
            raise ValueError("RUN_LEASE_SECONDS must be at least twice MODEL_TIMEOUT_SECONDS")
        return self

    @model_validator(mode="after")
    def check_fallback_is_a_configured_second_provider(self) -> Self:
        fallback = self.model_fallback_provider
        if fallback == "none":
            return self
        if fallback == self.model_provider or self.model_provider == "none":
            raise ValueError("MODEL_FALLBACK_PROVIDER must differ from a configured MODEL_PROVIDER")
        if self.fallback_model() is None:
            raise ValueError(
                f"MODEL_FALLBACK_PROVIDER={fallback} requires {fallback.upper()}_API_KEY"
            )
        return self

    @model_validator(mode="after")
    def check_model_provider_is_configured(self) -> Self:
        if self.model_provider != "none" and self.active_model() is None:
            name = self.model_provider.upper()
            raise ValueError(f"MODEL_PROVIDER={self.model_provider} requires {name}_API_KEY")
        return self

    @property
    def is_local_environment(self) -> bool:
        return self.app_env in LOCAL_ENVIRONMENTS

    def active_model(self, model_id: str | None = None) -> ModelConfig | None:
        """The selected provider's configuration, or None when none is configured.

        `model_id` overrides the configured model, for evaluations and probes.
        """
        if self.model_provider == "none":
            return None
        return self.provider_config(self.model_provider, model_id)

    def fallback_model(self) -> ModelConfig | None:
        if self.model_fallback_provider == "none":
            return None
        return self.provider_config(self.model_fallback_provider)

    def provider_config(
        self, provider: ProviderName, model_id: str | None = None
    ) -> ModelConfig | None:
        """A configured provider's settings, whether or not it is the selected one."""
        match provider:
            case "gemini" if self.gemini_api_key is not None:
                return ModelConfig(
                    provider="gemini",
                    model_id=model_id or self.gemini_model_id,
                    api_key=self.gemini_api_key.get_secret_value(),
                    timeout_seconds=self.model_timeout_seconds,
                    thinking_level=self.model_thinking_level,
                )
            case "groq" if self.groq_api_key is not None:
                return ModelConfig(
                    provider="groq",
                    model_id=model_id or self.groq_model_id,
                    api_key=self.groq_api_key.get_secret_value(),
                    timeout_seconds=self.model_timeout_seconds,
                    thinking_level=self.model_thinking_level,
                    base_url=self.groq_base_url,
                    max_output_tokens_cap=self.groq_max_output_tokens,
                    tokens_per_minute=self.groq_tokens_per_minute,
                )
            case _:
                return None


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

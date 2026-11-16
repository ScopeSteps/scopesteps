import secrets
from decimal import Decimal

import pytest
from pydantic import ValidationError

from scopesteps.api.main import ModelKeysMissingError, create_app
from scopesteps.api.modules import MODULE_NAMES
from scopesteps.api.settings import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sources,backlog", ["sources", "backlog"]),
        (" sources , backlog ,", ["sources", "backlog"]),
        ("", list(MODULE_NAMES)),
    ],
)
def test_enabled_modules_parses_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("ENABLED_MODULES", raw)

    assert Settings().enabled_modules == expected


def test_enabled_modules_rejects_unknown_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_MODULES", "sources,billing")

    with pytest.raises(ValidationError, match="billing"):
        Settings()


@pytest.mark.parametrize(
    ("app_env", "api_host"),
    [
        ("demo", "127.0.0.1"),
        ("production", "127.0.0.1"),
        ("local", "0.0.0.0"),  # noqa: S104
        ("local", "10.0.0.5"),
    ],
)
def test_local_auth_is_refused_outside_local_loopback(app_env: str, api_host: str) -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=local"):
        Settings.model_validate({"auth_mode": "local", "app_env": app_env, "api_host": api_host})


@pytest.mark.parametrize("api_host", ["127.0.0.1", "localhost", "::1"])
def test_local_auth_is_accepted_on_loopback(api_host: str) -> None:
    settings = Settings.model_validate(
        {"auth_mode": "local", "app_env": "local", "api_host": api_host}
    )

    assert settings.auth_mode == "local"


def test_session_auth_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)

    assert Settings().auth_mode == "session"


@pytest.mark.parametrize(
    ("app_env", "api_host"),
    [("local", "127.0.0.1"), ("production", "0.0.0.0"), ("demo", "10.0.0.5")],  # noqa: S104
)
def test_session_auth_is_accepted_in_every_environment(app_env: str, api_host: str) -> None:
    settings = Settings.model_validate(
        {"auth_mode": "session", "app_env": app_env, "api_host": api_host}
    )

    assert settings.auth_mode == "session"
    assert (settings.session_absolute_lifetime_minutes, settings.session_idle_timeout_minutes) == (
        720,
        120,
    )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"session_absolute_lifetime_minutes": 4}, "session_absolute_lifetime_minutes"),
        ({"session_absolute_lifetime_minutes": 10081}, "session_absolute_lifetime_minutes"),
        ({"session_idle_timeout_minutes": 0}, "session_idle_timeout_minutes"),
        (
            {"session_absolute_lifetime_minutes": 60, "session_idle_timeout_minutes": 61},
            "SESSION_IDLE_TIMEOUT_MINUTES must not exceed",
        ),
        ({"auth_mode": "sso"}, "auth_mode"),
    ],
)
def test_session_settings_are_validated(values: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(values)


def test_the_seed_account_password_is_unset_by_default_and_never_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = secrets.token_urlsafe(16)
    monkeypatch.setenv("SEED_ACCOUNT_PASSWORD", "")
    unset = Settings()
    monkeypatch.setenv("SEED_ACCOUNT_PASSWORD", password)

    configured = Settings()

    assert unset.seed_account_password is None
    assert configured.seed_account_password is not None
    assert configured.seed_account_password.get_secret_value() == password
    assert password not in repr(configured)
    assert password not in configured.model_dump_json()


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_the_selected_provider_needs_its_own_key(provider: str) -> None:
    with pytest.raises(ValidationError, match=f"{provider.upper()}_API_KEY"):
        Settings.model_validate({"model_provider": provider})


def test_each_provider_keeps_its_own_key_and_model() -> None:
    keys = {"gemini_api_key": "gemini-secret", "groq_api_key": "groq-secret"}

    gemini = Settings.model_validate({"model_provider": "gemini", **keys}).active_model()
    groq = Settings.model_validate({"model_provider": "groq", **keys}).active_model()

    assert gemini is not None
    assert (gemini.provider, gemini.model_id, gemini.api_key) == (
        "gemini",
        "gemini-3.5-flash-lite",
        "gemini-secret",
    )
    assert groq is not None
    assert (groq.provider, groq.model_id, groq.api_key) == (
        "groq",
        "openai/gpt-oss-120b",
        "groq-secret",
    )
    assert groq.max_output_tokens_cap == 6000
    assert Settings.model_validate(keys).active_model() is None, "none by default"


def test_api_keys_are_never_rendered() -> None:
    settings = Settings.model_validate(
        {"model_provider": "groq", "groq_api_key": "secret-value", "gemini_api_key": "other"}
    )
    model = settings.active_model()

    for rendered in (repr(settings), settings.model_dump_json(), repr(model)):
        assert "secret-value" not in rendered
        assert "other" not in rendered


@pytest.mark.parametrize(
    "field",
    [
        "run_max_turns",
        "run_max_total_tokens",
        "source_max_bytes",
        "source_max_document_bytes",
        "run_cost_limit_usd",
        "model_timeout_seconds",
    ],
)
def test_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings.model_validate({field: 0})


@pytest.mark.parametrize(("value", "valid"), [("low", True), ("high", True), ("max", False)])
def test_model_thinking_level_is_restricted(value: str, valid: bool) -> None:
    if valid:
        assert (
            Settings.model_validate({"model_thinking_level": value}).model_thinking_level == value
        )
    else:
        with pytest.raises(ValidationError, match="model_thinking_level"):
            Settings.model_validate({"model_thinking_level": value})


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"model_provider": "gemini", "model_fallback_provider": "gemini"}, "must differ"),
        ({"model_provider": "none", "model_fallback_provider": "groq"}, "must differ"),
        ({"model_provider": "gemini", "model_fallback_provider": "groq"}, "GROQ_API_KEY"),
    ],
)
def test_the_fallback_must_be_a_second_configured_provider(
    values: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate({"gemini_api_key": "g", **values})


def test_a_configured_fallback_has_its_own_model() -> None:
    settings = Settings.model_validate(
        {
            "model_provider": "gemini",
            "model_fallback_provider": "groq",
            "gemini_api_key": "g",
            "groq_api_key": "q",
        }
    )

    fallback = settings.fallback_model()
    assert fallback is not None
    assert (fallback.provider, fallback.model_id) == ("groq", "openai/gpt-oss-120b")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"app_env": "demo"}, "APP_ENV=local or test"),
        ({"app_env": "production"}, "APP_ENV=local or test"),
        ({"model_replay_file": None}, "requires MODEL_REPLAY_FILE"),
    ],
)
def test_a_replay_is_local_only_and_needs_its_recording(
    values: dict[str, object], message: str
) -> None:
    replay = {"model_profile": "replay", "app_env": "local", "model_replay_file": "demo.json"}
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(replay | values)


@pytest.mark.parametrize("app_env", ["local", "production"])
def test_the_scripted_profile_is_for_tests_only(app_env: str) -> None:
    with pytest.raises(ValidationError, match="requires APP_ENV=test"):
        Settings.model_validate(
            {"model_profile": "fake", "app_env": app_env, "auth_mode": "session"}
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"app_env": "production", "auth_mode": "session"}, "APP_ENV=local or test"),
        ({"model_profile": "replay", "model_replay_file": "demo.json"}, "a live MODEL_PROFILE"),
    ],
)
def test_recording_is_local_only_and_needs_a_live_profile(
    values: dict[str, object], message: str
) -> None:
    record = {"app_env": "local", "model_record_file": "demo.json"}
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(record | values)


def test_new_runs_use_the_claude_mix_profile_by_default() -> None:
    settings = Settings.model_validate({})

    assert settings.profile().id == "claude-mix-v1"


def test_an_unknown_profile_is_refused() -> None:
    with pytest.raises(ValidationError, match="Unknown MODEL_PROFILE"):
        Settings.model_validate({"model_profile": "gemini-flash-lite"})


@pytest.mark.parametrize(("lease", "valid"), [(839, False), (840, True), (900, True)])
def test_the_lease_must_outlast_two_calls_of_the_slowest_step(lease: int, valid: bool) -> None:
    values = {"model_profile": "claude-mix-v1", "run_lease_seconds": lease}
    if valid:
        assert Settings.model_validate(values).run_lease_seconds == lease
    else:
        with pytest.raises(ValidationError, match="twice the longest step timeout"):
            Settings.model_validate(values)


@pytest.mark.parametrize(
    ("values", "missing"),
    [
        ({"model_profile": "claude-mix-v1"}, ["ANTHROPIC_API_KEY"]),
        ({"model_profile": "claude-mix-v1", "anthropic_api_key": "test-key"}, []),
        ({"model_profile": "fake", "app_env": "test"}, []),
        ({"model_profile": "replay", "app_env": "test", "model_replay_file": "demo.json"}, []),
    ],
)
def test_the_profile_lists_the_keys_it_still_needs(
    values: dict[str, object], missing: list[str]
) -> None:
    assert Settings.model_validate(values).missing_model_keys() == missing


def test_the_api_refuses_to_start_without_a_key_its_profile_needs() -> None:
    settings = Settings.model_validate(
        {"app_env": "test", "database_url": "sqlite://", "model_profile": "claude-mix-v1"}
    )

    with pytest.raises(ModelKeysMissingError, match="ANTHROPIC_API_KEY"):
        create_app(settings)


def test_paid_model_defaults_cap_cost_and_outlast_the_longest_step() -> None:
    settings = Settings.model_validate({})

    assert settings.run_cost_limit_usd == Decimal("1.50")
    assert settings.project_cost_limit_usd == Decimal("25")
    assert settings.run_lease_seconds == 900


def test_anthropic_key_is_never_rendered() -> None:
    settings = Settings.model_validate({"anthropic_api_key": "sk-ant-secret-value"})

    for rendered in (repr(settings), settings.model_dump_json()):
        assert "sk-ant-secret-value" not in rendered

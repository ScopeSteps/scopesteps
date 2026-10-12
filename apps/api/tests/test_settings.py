import pytest
from pydantic import ValidationError

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
        Settings.model_validate({"app_env": app_env, "api_host": api_host})


@pytest.mark.parametrize("api_host", ["127.0.0.1", "localhost", "::1"])
def test_local_auth_is_accepted_on_loopback(api_host: str) -> None:
    assert Settings.model_validate({"app_env": "local", "api_host": api_host}).auth_mode == "local"


def test_model_provider_requires_model_id_and_key() -> None:
    with pytest.raises(ValidationError, match="MODEL_PROVIDER=gemini"):
        Settings.model_validate({"model_provider": "gemini", "model_id": "gemini-x"})


def test_model_api_key_is_never_rendered() -> None:
    settings = Settings.model_validate(
        {"model_provider": "gemini", "model_id": "gemini-x", "model_api_key": "secret-value"}
    )

    assert "secret-value" not in repr(settings)
    assert "secret-value" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "run_max_turns",
        "run_max_total_tokens",
        "source_max_bytes",
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

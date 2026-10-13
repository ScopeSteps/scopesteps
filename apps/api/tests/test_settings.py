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

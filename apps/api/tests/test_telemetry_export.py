from collections.abc import Callable
from typing import cast

import pytest
from fastapi.testclient import TestClient

from scopesteps.agent.client import AgentRuntime, Telemetry
from scopesteps.api.settings import Settings

ClientFactory = Callable[..., TestClient]

HEADERS = "authorization=Bearer synthetic-otlp-key"


def test_without_an_endpoint_nothing_is_exported(
    monkeypatch: pytest.MonkeyPatch, migrated_database_url: str, make_client: ClientFactory
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    client = make_client(migrated_database_url)

    assert Settings().otlp_export() is None
    assert client.app.state.telemetry is None  # type: ignore[attr-defined]


def test_an_endpoint_turns_export_on_and_shutting_down_flushes_it(
    monkeypatch: pytest.MonkeyPatch, migrated_database_url: str, make_client: ClientFactory
) -> None:
    shut_down: list[Telemetry] = []

    def record_shutdown(self: Telemetry) -> None:
        shut_down.append(self)

    monkeypatch.setattr(Telemetry, "shutdown", record_shutdown)

    client = make_client(
        migrated_database_url,
        otel_exporter_otlp_endpoint="http://127.0.0.1:9",
        otel_exporter_otlp_headers=HEADERS,
    )
    telemetry: object = client.app.state.telemetry  # type: ignore[attr-defined]
    client.__exit__(None, None, None)

    assert isinstance(telemetry, Telemetry)
    assert shut_down == [telemetry]


def test_with_export_on_the_circuit_breaker_sends_its_openings_to_the_sink(
    monkeypatch: pytest.MonkeyPatch, migrated_database_url: str, make_client: ClientFactory
) -> None:
    def no_shutdown(self: Telemetry) -> None:
        return None

    monkeypatch.setattr(Telemetry, "shutdown", no_shutdown)

    client = make_client(migrated_database_url, otel_exporter_otlp_endpoint="http://127.0.0.1:9")
    runtime = cast(AgentRuntime, client.app.state.agent_runtime)  # type: ignore[attr-defined]
    telemetry = cast(Telemetry, client.app.state.telemetry)  # type: ignore[attr-defined]

    assert runtime.breaker.sink is telemetry.sink


def test_without_export_the_circuit_breaker_only_logs(
    monkeypatch: pytest.MonkeyPatch, migrated_database_url: str, make_client: ClientFactory
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    client = make_client(migrated_database_url)
    runtime = cast(AgentRuntime, client.app.state.agent_runtime)  # type: ignore[attr-defined]

    assert runtime.breaker.sink is None


def test_the_otlp_settings_use_the_standard_names_and_hide_the_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", HEADERS)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "scopesteps-demo")

    settings = Settings()
    config = settings.otlp_export()

    assert config is not None
    assert (config.endpoint, config.service_name, config.headers) == (
        "http://127.0.0.1:4318",
        "scopesteps-demo",
        HEADERS,
    )
    assert "synthetic-otlp-key" not in repr(settings)
    assert "synthetic-otlp-key" not in repr(config)

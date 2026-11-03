import json
import logging
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

import pytest
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from scopesteps.agent.application.tracing import trace_scope
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelTurn,
    Usage,
    UserMessage,
)
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.providers.traced import TracedProvider, log_sink
from scopesteps.agent.infrastructure.telemetry import (
    EXPORTED_ATTRIBUTES,
    OtlpConfig,
    Telemetry,
    build_telemetry,
    otlp_telemetry,
)

PRIVATE_SOURCE = "CONFIDENTIAL source sentence"
PRIVATE_ERROR = "quota exceeded for CONFIDENTIAL project"
REQUEST = ModelRequest(
    system_instruction="policy text", history=(UserMessage(PRIVATE_SOURCE),), max_output_tokens=50
)
RESULT = ModelResult(
    provider="gemini",
    model_id="gemini-3.5-flash-lite-001",
    turn=ModelTurn(({"type": "model_output", "text": "MODEL OUTPUT"},)),
    text="MODEL OUTPUT",
    tool_calls=(),
    finish_reason="completed",
    usage=Usage(input_tokens=1200, output_tokens=300, thinking_tokens=40),
    latency_ms=1500,
)


@pytest.fixture
def exported() -> tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader]:
    spans = InMemorySpanExporter()
    metrics = InMemoryMetricReader()
    return build_telemetry(SimpleSpanProcessor(spans), metrics, "scopesteps-test"), spans, metrics


def _provider(
    script: Sequence[ModelResult | ModelProviderError], sink: Any
) -> tuple[TracedProvider, list[dict[str, Any]]]:
    """A traced provider writing to `sink` and, beside it, the events it was given."""
    events: list[dict[str, Any]] = []

    def both(event: dict[str, Any]) -> None:
        events.append(dict(event))
        sink(event)

    provider = TracedProvider(
        ScriptedProvider(list(script)),
        provider_name="gcp.gemini",
        model_id="gemini-3.5-flash-lite",
        sink=both,
    )
    return provider, events


def _labels(point: HistogramDataPoint) -> dict[str, Any]:
    return dict(point.attributes or {})


def _histogram(reader: InMemoryMetricReader, name: str) -> list[HistogramDataPoint]:
    data = reader.get_metrics_data()
    assert data is not None
    return [
        point
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
        if isinstance(point, HistogramDataPoint)
    ]


def test_without_export_model_calls_go_to_the_log_as_before(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = TracedProvider(
        ScriptedProvider([RESULT]),
        provider_name="gcp.gemini",
        model_id="gemini-3.5-flash-lite",
        sink=log_sink,
    )

    with caplog.at_level(logging.INFO, logger="scopesteps.agent.model_calls"):
        result = provider.generate(REQUEST)

    assert result == RESULT
    (record,) = caplog.records
    event = json.loads(record.getMessage())
    assert event["name"] == "gen_ai.chat"
    assert event["gen_ai.usage.input_tokens"] == 1200


def test_each_call_is_one_genai_client_span_with_the_log_events_attributes(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, spans, _ = exported
    provider, events = _provider([RESULT], telemetry.sink)

    with (
        trace_scope(run_id="r1", stage="draft", prompt_version="draft-v10"),
        trace_scope(attempt=1, repair=False),
    ):
        provider.generate(REQUEST)

    (span,) = spans.get_finished_spans()
    (event,) = events
    assert span.name == "chat gemini-3.5-flash-lite"
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.UNSET
    expected: dict[str, Any] = {
        key: tuple(cast(list[object], value)) if isinstance(value, list) else value
        for key, value in event.items()
        if key not in {"name", "duration_ms"} and value is not None
    }
    assert dict(span.attributes or {}) == expected
    assert span.end_time is not None
    assert span.start_time is not None
    assert span.end_time - span.start_time == 1500 * 1_000_000, "the call's own duration"
    assert span.resource.attributes["service.name"] == "scopesteps-test"


def test_a_failed_call_is_one_error_span_without_its_message(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, spans, metrics = exported
    provider, _ = _provider([ModelProviderError("quota", PRIVATE_ERROR)], telemetry.sink)

    with pytest.raises(ModelProviderError):
        provider.generate(REQUEST)

    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert (span.attributes or {})["error.type"] == "quota"
    assert not span.events, "no exception event, which would carry the message"
    assert PRIVATE_ERROR not in json.dumps(span.to_json())
    (point,) = _histogram(metrics, "gen_ai.client.operation.duration")
    assert _labels(point)["error.type"] == "quota"


def test_duration_and_token_usage_are_genai_client_histograms(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, _, metrics = exported
    provider, _ = _provider([RESULT, replace(RESULT, latency_ms=500)], telemetry.sink)

    provider.generate(REQUEST)
    provider.generate(REQUEST)

    (duration,) = _histogram(metrics, "gen_ai.client.operation.duration")
    assert (duration.count, duration.sum) == (2, pytest.approx(2.0))
    assert _labels(duration) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "gcp.gemini",
        "gen_ai.request.model": "gemini-3.5-flash-lite",
        "gen_ai.response.model": "gemini-3.5-flash-lite-001",
    }
    tokens = {
        _labels(point)["gen_ai.token.type"]: point.sum
        for point in _histogram(metrics, "gen_ai.client.token.usage")
    }
    assert tokens == {"input": 2400, "output": 600}


def test_only_allow_listed_attributes_are_exported(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, spans, metrics = exported
    provider, _ = _provider([RESULT, ModelProviderError("timeout", PRIVATE_ERROR)], telemetry.sink)

    # A scope attribute nobody reviewed, carrying text it never should.
    with trace_scope(run_id="r1", pack="campus", mode="agent", repeat=1, note=PRIVATE_SOURCE):
        provider.generate(REQUEST)
        with pytest.raises(ModelProviderError):
            provider.generate(REQUEST)

    finished = spans.get_finished_spans()
    assert len(finished) == 2
    for span in finished:
        assert set(span.attributes or {}) <= EXPORTED_ATTRIBUTES
        serialized = span.to_json()
        for text in (PRIVATE_SOURCE, "policy text", "MODEL OUTPUT", PRIVATE_ERROR):
            assert text not in serialized
    metric_keys = {
        key
        for name in ("gen_ai.client.operation.duration", "gen_ai.client.token.usage")
        for point in _histogram(metrics, name)
        for key in _labels(point)
    }
    assert metric_keys <= EXPORTED_ATTRIBUTES | {"gen_ai.token.type"}


class _FailingExporter(SpanExporter):
    def __init__(self) -> None:
        self.attempts = 0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.attempts += 1
        raise ConnectionError("collector unreachable")


def test_a_failing_collector_never_fails_or_delays_a_call() -> None:
    exporter = _FailingExporter()
    telemetry = build_telemetry(
        BatchSpanProcessor(exporter, schedule_delay_millis=10), InMemoryMetricReader(), "test"
    )
    provider, _ = _provider([RESULT], telemetry.sink)

    result = provider.generate(REQUEST)
    telemetry.tracer_provider.force_flush()

    assert result == RESULT
    assert exporter.attempts >= 1, "the span was handed to the exporter, in the background"
    telemetry.shutdown()


def test_an_unreachable_otlp_endpoint_does_not_slow_a_call() -> None:
    # Port 9 (discard) is closed on a development machine and in CI.
    telemetry = otlp_telemetry(OtlpConfig(endpoint="http://127.0.0.1:9", timeout_seconds=1))
    provider, _ = _provider([RESULT], telemetry.sink)

    started = time.perf_counter()
    result = provider.generate(REQUEST)
    elapsed = time.perf_counter() - started

    assert result == RESULT
    assert elapsed < 0.5
    telemetry.shutdown()


def test_a_broken_event_is_dropped_without_failing_the_call(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
    caplog: pytest.LogCaptureFixture,
) -> None:
    telemetry, spans, _ = exported

    with caplog.at_level(logging.WARNING, logger="scopesteps.agent.telemetry"):
        telemetry.sink({"name": "gen_ai.chat", "duration_ms": 3})

    assert not spans.get_finished_spans()
    assert "KeyError" in caplog.text


def test_headers_are_kept_out_of_the_configs_repr() -> None:
    config = OtlpConfig(endpoint="http://127.0.0.1:4318", headers="authorization=Bearer secret")

    assert "secret" not in repr(config)


RUN_RECORD: dict[str, Any] = {
    "name": "scopesteps.agent.run",
    "duration_ms": 8000,
    "error.type": "CHANGE_REJECTED",
    "scopesteps.run_id": "r9",
    "scopesteps.run.kind": "change",
    "scopesteps.run.status": "failed",
    "scopesteps.prompt_version": "change-v7+abc",
    "scopesteps.run.provider": "gemini",
    "scopesteps.run.model": "gemini-3.5-flash-lite",
    "scopesteps.run.served_by": "primary",
    "scopesteps.replay": False,
    "scopesteps.run.model_turns": 3,
    "scopesteps.run.total_tokens": 21000,
    "scopesteps.cost_usd_estimate": "0.012000",
    "scopesteps.run.problems": 2,
    "scopesteps.run.problem_codes": ["over_limit", "unknown_block"],
    "scopesteps.run.repaired": True,
    "scopesteps.run.questions": 1,
}


def _sum(reader: InMemoryMetricReader, name: str) -> list[tuple[dict[str, Any], float]]:
    data = reader.get_metrics_data()
    assert data is not None
    return [
        (dict(point.attributes or {}), float(getattr(point, "sum", getattr(point, "value", 0))))
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


def test_a_run_outcome_is_one_span_a_run_count_and_problem_and_cost_histograms(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, spans, metrics = exported

    telemetry.sink(dict(RUN_RECORD))
    telemetry.sink(RUN_RECORD | {"scopesteps.replay": True, "scopesteps.run.provider": "replay"})

    first, _ = spans.get_finished_spans()
    assert first.name == "agent_run change"
    assert first.kind is SpanKind.INTERNAL
    assert first.status.status_code is StatusCode.ERROR
    assert (first.attributes or {})["scopesteps.run.problem_codes"] == (
        "over_limit",
        "unknown_block",
    )
    assert first.end_time is not None
    assert first.start_time is not None
    assert first.end_time - first.start_time == 8000 * 1_000_000
    counts = _sum(metrics, "scopesteps.agent.runs")
    assert sorted((labels["scopesteps.replay"], value) for labels, value in counts) == [
        (False, 1),
        (True, 1),
    ]
    labels, _ = counts[0]
    assert "scopesteps.run_id" not in labels, "no series per run"
    assert labels["scopesteps.run.status"] == "failed"
    assert labels["error.type"] == "CHANGE_REJECTED"
    assert sorted(value for _, value in _sum(metrics, "scopesteps.agent.run.problems")) == [2, 2]
    assert sorted(value for _, value in _sum(metrics, "scopesteps.agent.run.cost")) == [
        pytest.approx(0.012),
        pytest.approx(0.012),
    ]


def test_a_run_outcome_exports_only_allow_listed_attributes(
    exported: tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    telemetry, spans, metrics = exported

    telemetry.sink(RUN_RECORD | {"scopesteps.run.answer": PRIVATE_SOURCE})

    (span,) = spans.get_finished_spans()
    assert set(span.attributes or {}) <= EXPORTED_ATTRIBUTES
    assert PRIVATE_SOURCE not in span.to_json()
    for name in ("scopesteps.agent.runs", "scopesteps.agent.run.problems"):
        for labels, _ in _sum(metrics, name):
            assert set(labels) <= EXPORTED_ATTRIBUTES

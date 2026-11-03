"""Model-call events exported over OTLP as OpenTelemetry GenAI spans and metrics (ADR 0022).

The sink receives the same content-free event `TracedProvider` writes to the log and exports only
the attributes in `EXPORTED_ATTRIBUTES`, so a key added to an event later stays local until it is
reviewed and listed here. Spans and metrics leave in the background: a slow, unreachable or
failing collector never delays or fails a model call.
"""

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.util.re import parse_env_headers

from scopesteps.agent.infrastructure.providers.traced import MODEL_CALL_EVENT

_logger = logging.getLogger("scopesteps.agent.telemetry")
_SCOPE = "scopesteps.agent"

# Every key `TracedProvider` and the `trace_scope` callers set. Ids, versions, counts, codes and
# durations only; never prompts, source text, answers or model output.
EXPORTED_ATTRIBUTES = frozenset(
    {
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.request.max_tokens",
        "gen_ai.response.model",
        "gen_ai.response.finish_reasons",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "error.type",
        "scopesteps.structured_output",
        "scopesteps.tools_offered",
        "scopesteps.history_turns",
        "scopesteps.retryable",
        "scopesteps.usage.thinking_tokens",
        "scopesteps.tool_calls",
        "scopesteps.cost_usd_estimate",
        "scopesteps.run_id",
        "scopesteps.stage",
        "scopesteps.prompt_version",
        "scopesteps.attempt",
        "scopesteps.repair",
        "scopesteps.pack",
        "scopesteps.mode",
        "scopesteps.repeat",
        "scopesteps.prompt_variant",
    }
)
# The GenAI client metrics' attributes: low-cardinality, so no run id on a metric.
METRIC_ATTRIBUTES = (
    "gen_ai.operation.name",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "error.type",
)
# The bucket boundaries the GenAI semantic conventions recommend for each metric.
DURATION_BUCKETS_SECONDS = (
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
)  # fmt: skip
TOKEN_BUCKETS = (
    1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864,
)  # fmt: skip


@dataclass(frozen=True)
class OtlpConfig:
    """Where to export, from the standard `OTEL_*` settings. `endpoint` is the collector's base
    URL; the signal paths (`/v1/traces`, `/v1/metrics`) are added as the OTLP spec says.
    `headers` keeps the `OTEL_EXPORTER_OTLP_HEADERS` format: `key=value` pairs, comma-separated."""

    endpoint: str
    service_name: str = "scopesteps-api"
    headers: str | None = field(default=None, repr=False)
    timeout_seconds: float = 10


class OpenTelemetrySink:
    """A `TraceSink` that records each model-call event as one GenAI client span and the
    `gen_ai.client.operation.duration` and `gen_ai.client.token.usage` histograms."""

    def __init__(self, tracer_provider: TracerProvider, meter_provider: MeterProvider) -> None:
        self._tracer = tracer_provider.get_tracer(_SCOPE)
        meter = meter_provider.get_meter(_SCOPE)
        self._duration = meter.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="GenAI operation duration",
            explicit_bucket_boundaries_advisory=DURATION_BUCKETS_SECONDS,
        )
        self._tokens = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Number of input and output tokens used",
            explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
        )

    def __call__(self, event: dict[str, Any]) -> None:
        try:
            if event.get("name") == MODEL_CALL_EVENT:
                self._model_call(event)
        except Exception as error:
            # The type only: an exception's text could quote what it was given.
            _logger.warning("Could not export a telemetry event (%s)", type(error).__name__)

    def _model_call(self, event: Mapping[str, Any]) -> None:
        attributes = exported_attributes(event)
        duration_ms = int(event.get("duration_ms") or 0)
        end = time.time_ns()
        span = self._tracer.start_span(
            f"{event['gen_ai.operation.name']} {event['gen_ai.request.model']}",
            kind=SpanKind.CLIENT,
            start_time=end - duration_ms * 1_000_000,
            attributes=attributes,
        )
        if "error.type" in attributes:
            # No description: the error's message is never recorded.
            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end)

        labels = {key: attributes[key] for key in METRIC_ATTRIBUTES if key in attributes}
        self._duration.record(duration_ms / 1000, labels)
        for token_type, key in (
            ("input", "gen_ai.usage.input_tokens"),
            ("output", "gen_ai.usage.output_tokens"),
        ):
            if key in attributes:
                self._tokens.record(attributes[key], labels | {"gen_ai.token.type": token_type})


def exported_attributes(event: Mapping[str, Any]) -> dict[str, Any]:
    """The allow-listed, non-empty attributes of an event, in a form OpenTelemetry accepts."""
    exported: dict[str, Any] = {}
    for key, value in event.items():
        if key not in EXPORTED_ATTRIBUTES or value is None:
            continue
        # OpenTelemetry takes sequences as tuples; events hold lists (finish reasons).
        exported[key] = tuple(cast(list[object], value)) if isinstance(value, list) else value
    return exported


@dataclass(frozen=True)
class Telemetry:
    """The export pipeline the API owns: its sink, and a shutdown that flushes what is queued."""

    sink: OpenTelemetrySink
    tracer_provider: TracerProvider
    meter_provider: MeterProvider

    def shutdown(self) -> None:
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


def build_telemetry(
    span_processor: SpanProcessor, metric_reader: MetricReader, service_name: str
) -> Telemetry:
    """A pipeline over the given processor and reader; tests pass in-memory ones."""
    resource = Resource.create({SERVICE_NAME: service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    return Telemetry(
        sink=OpenTelemetrySink(tracer_provider, meter_provider),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def otlp_telemetry(config: OtlpConfig) -> Telemetry:
    """Export over OTLP/HTTP: spans in batches and metrics every 60 seconds, both from background
    threads, so a call never waits for the collector."""
    base = config.endpoint.rstrip("/")
    headers = parse_env_headers(config.headers or "", liberal=True)
    return build_telemetry(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{base}/v1/traces", headers=headers, timeout=config.timeout_seconds
            )
        ),
        PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=f"{base}/v1/metrics", headers=headers, timeout=config.timeout_seconds
            )
        ),
        config.service_name,
    )

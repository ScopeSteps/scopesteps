# 0022. Export model-call telemetry over OTLP to a vendor-neutral backend

- Status: Accepted
- Date: 2026-11-03

## Context

Every model call already emits one content-free event with OpenTelemetry GenAI attribute names
(`gen_ai.*`), but only to the API log. Nothing can chart latency, tokens, cost or errors over time,
and nothing can alert when agent runs drift from what the evaluations measured. Sara's supervisor
asked on 2026-10-28 whether agent outcomes are flagged below thresholds. This is the first of three
tasks: model calls here, run outcomes next, then alert rules set from evaluation results.

## Decision

- **Export over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.** The API then records each
  model call as one GenAI client span (`chat <model>`) and in the GenAI client metrics
  `gen_ai.client.operation.duration` and `gen_ai.client.token.usage`, with the buckets the
  conventions recommend. Unset, the events go to the log exactly as before. The standard
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` and `OTEL_SERVICE_NAME` are read
  through the API's settings, so `.env` reaches them; the headers are a secret.
- **Vendor-neutral.** The app speaks only OTLP, so any backend that accepts it (a collector,
  Grafana, Honeycomb, Datadog, a cloud's own) is a settings change. No vendor SDK is added.
- **Content-free by an allow-list.** The span carries the log event's attributes, but only those
  in `EXPORTED_ATTRIBUTES` (`modules/agent/.../infrastructure/telemetry.py`). A key added to an
  event later stays in the log until it is reviewed and listed. A failed call's span has error
  status and `error.type`, never the error's message. Metrics carry only low-cardinality labels:
  operation, provider, models and error type.
- **Telemetry never fails a call.** Spans are batched and metrics read every 60 seconds, both from
  background threads; a sink error is logged by its type and dropped. Shutting the API down
  flushes what is queued.
- **A local backend in Docker.** `just telemetry` starts `grafana/otel-lgtm` (a collector with
  Tempo, Prometheus and Grafana in one container) on 4318, with Grafana at
  http://localhost:3000. It keeps nothing after it stops.
- **Evaluations and probes are unchanged.** They keep writing `traces.jsonl` (evaluations) or
  discarding events (probes); they never export.

## Consequences

- Model calls can be charted and queried by provider, model, stage, prompt version and error.
- The alert rules of SSPOC-119 can be written against these metrics and the run outcomes of
  SSPOC-118 without changing the app.
- A new trace attribute takes two edits: set it, then add it to `EXPORTED_ATTRIBUTES` after
  checking it carries no content.
- Exported spans hold run ids. They identify a run, not a person, but a hosted backend still
  receives them: choose one whose data terms fit, as for a model provider (ADR 0004).
- A process killed without shutdown (as Playwright stops the API after `just e2e`) loses the last
  few seconds of spans and the metrics not yet read.

## Notes

2026-11-03 (SSPOC-118): each finished run also sends one outcome record through the same sink:
one `agent_run <kind>` span, the `scopesteps.agent.runs` counter and the
`scopesteps.agent.run.problems` and `scopesteps.agent.run.cost` histograms, or one log line on
`scopesteps.agent.runs` with export off. It is emitted after the transaction that stores the
outcome commits, its attributes are on the same allow-list, and replayed runs are labelled
`scopesteps.replay` so they can be left out of charts and alerts. Nothing else changes.

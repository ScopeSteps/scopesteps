# 0023. Alert rules as code, with thresholds set from evaluation results

- Status: Accepted
- Date: 2026-11-03

## Context

Model calls and finished runs are exported over OTLP ([ADR 0022](0022-export-model-call-telemetry-over-otlp.md)),
but nothing says when they drift from what the evaluations measured. Sara's supervisor asked on
2026-10-28 whether agent outcomes are flagged below thresholds. The checks must run in the
monitoring backend, not in application code, be kept in the repository, be testable without a
model, and notify only locally in the POC. POC traffic is low, so a rule must not fire on one bad
run among a handful.

## Decision

- **Prometheus alerting rules, in `ops/monitoring/alerts.yaml`.** They are the open format most
  backends load (Prometheus, Grafana, Mimir, the clouds' managed Prometheus). The Prometheus in
  the local backend (`grafana/otel-lgtm`) loads them through `ops/monitoring/prometheus.yaml`,
  the image's own configuration plus the rule file and an Alertmanager.
- **Six rules, all on exported metrics:** run failure rate, p95 model-call latency, share of
  calls cut off by the output limit, mean estimated cost per run and mean problems left after
  repair (both per run kind), and the backup circuit opening. Each states its threshold, window,
  minimum number of finished runs, severity, the evaluation it comes from (evals/README.md
  section and report stamp) and a runbook link
  ([docs/runbooks/agent-alerts.md](../runbooks/agent-alerts.md)). Replays are left out.
- **Thresholds come from the dev evaluation reports**, computed by `just evals-baselines`: a
  rate is set at the upper end of the evaluation's 95% interval, a mean cost at twice the
  evaluation mean, mean problems at the evaluation mean. They are reviewed whenever a prompt is
  adopted. Two levels proposed in the ticket were changed by the evidence: p95 latency is 25 s,
  not 60 s, because a call times out at 30 s and 60 s could never be reached; the cut-off share
  is 12%, not 5%, because the adopted draft prompt already cuts off 5% of calls in evaluation.
- **Tested with `promtool test rules`** (`ops/monitoring/alerts.test.yaml`): each rule fires on
  synthetic series above its threshold and stays quiet below it and below its minimum number of
  runs. `just alerts-check` and a CI job run it in the pinned `prom/prometheus` image; pytest
  checks the rules' metadata.
- **Notifications stay local.** Prometheus sends alerts to a local Alertmanager
  (`prom/alertmanager`), whose only receiver emails the Mailpit inbox. A real channel is a new
  receiver in `ops/monitoring/alertmanager.yaml` (see the runbook).
- **Counters start from zero.** Prometheus runs with `created-timestamp-zero-ingestion`, so the
  first run or circuit opening after an API start is counted by `increase()` instead of being
  taken as the series' first value. The feature is experimental in Prometheus 3.15.
- **Two metrics added to the app for it:** a `scopesteps.finish_reason` label on the GenAI
  client metrics, and the `scopesteps.agent.circuit.openings` counter (ADR 0022, note of
  2026-11-03).

## Consequences

- A drift from the evaluated behaviour is noticed in the backend, before a reviewer reports it.
- A prompt adoption has one more step: run `just evals-baselines` on its report and update the
  thresholds, their sources and the tests in the same pull request.
- `just alerts-check` and the local backend need Docker; `just check` does not run the promtool
  tests, CI does.
- The rules are written for the metric names Prometheus gives OTLP metrics (dots become
  underscores, units and `_total` are appended). A backend that names them differently needs the
  names adapted.
- The draft cost baseline is from single-pass drafting; a full agent run adds an explore step
  (about 1.3 times the cost in the 2026-10-13 agent runs). A current `just evals-agent` report
  would give a direct baseline.
- The circuit breaker is per process, so with several API instances the rule fires on any one.

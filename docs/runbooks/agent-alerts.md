# Agent alerts runbook

What each agent alert means, how to check it and what to do. The rules are in
[ops/monitoring/alerts.yaml](../../ops/monitoring/alerts.yaml)
([ADR 0023](../adr/0023-alert-rules-as-code-from-evaluation-results.md)); each threshold comes from
a recorded evaluation (evals/README.md, "Alert thresholds").

## Where alerts show up

`just telemetry` starts the local backend: Prometheus evaluates the rules every minute, and
Alertmanager emails each firing or resolved alert to the local test inbox.

| Where                                | What you see                                                       |
| ------------------------------------ | ------------------------------------------------------------------ |
| http://localhost:8025 (Mailpit)      | One email per alert group, `[FIRING:1] <alert> (<severity>)`       |
| http://localhost:9093 (Alertmanager) | Active alerts; silence one here while you work on it               |
| http://localhost:9090/alerts         | Every rule, its state (inactive, pending, firing) and its value    |
| http://localhost:3000 (Grafana)      | Alerting, Alert rules: the same rules, under the Prometheus source |

The API exports only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (see the agent module's README,
"Telemetry"). Replays (`just e2e`, the demo backup) are left out of every rule.

Every rule needs a minimum number of finished runs in its window before it can fire: with few
runs, one bad run is not a trend. A rule that fires has also held for 5 minutes (the circuit rule
fires at once). Severity is `critical` (runs are failing for people) or `warning` (worse or dearer
than evaluated, but working).

## Checking an alert

For any alert, these help:

- **Prometheus** (http://localhost:9090): paste the rule's expression from `alerts.yaml` and
  drop the threshold to see the current value. Group by a label to find the cause, for example
  `sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_runs_total{scopesteps_run_status="failed"}[1h]))`.
- **Tempo** in Grafana Explore: `{name=~"agent_run.*" && status=error}` lists failed runs with
  their `error.type`; `{name=~"chat.*"}` lists model calls with duration and finish reason.
- **The API log**: run and call events carry the same ids and codes, never content.
- **What changed**: a new prompt version, model, provider or price shows up as a new
  `scopesteps_prompt_version` or `scopesteps_run_model` label value.

## AgentRunFailureRateHigh

**What it means.** More than 10% of agent runs that finished in the last hour failed, over at
least 10 runs. Evaluations fail about 1 run in 50. People get an error instead of a draft, a
change set or a reply.

**How to check.** Find the error codes:
`sum by (error_type, scopesteps_run_kind) (increase(scopesteps_agent_runs_total{scopesteps_run_status="failed", scopesteps_replay="false"}[1h]))`.

- `MODEL_TIMEOUT`, `MODEL_UNAVAILABLE`, `MODEL_QUOTA`: the provider is slow, down or out of quota.
  See ModelCallLatencyHigh and BackupCircuitOpened, and the provider's status page.
- `INVALID_MODEL_OUTPUT`: the model's answers no longer pass the output schema, often because
  they were cut off (see ModelCallsCutOff). Look for a new prompt version or model in the labels.
- `RUN_BUDGET_EXCEEDED`: runs hit the turn, token or cost limits in settings; see AgentRunCostHigh.

**What to do.** For a provider outage, configure the backup provider (`MODEL_FALLBACK_PROVIDER`,
ADR 0006) or wait it out; failed runs can be started again. For output errors after a change,
roll back the prompt or model and measure it with the evaluations before trying again. Never raise
the threshold to quiet the alert.

## ModelCallLatencyHigh

**What it means.** The 95th percentile model call took more than 25 seconds over the last 15
minutes, over at least 5 runs. Evaluated draft calls take 16 seconds at p95, and a call that
reaches 30 seconds times out (`MODEL_TIMEOUT_SECONDS`), so runs are close to failing.

**How to check.** Split the latency by provider and model:
`histogram_quantile(0.95, sum by (le, gen_ai_provider_name, gen_ai_response_model) (rate(gen_ai_client_operation_duration_seconds_bucket[15m])))`.
Check whether timeouts are rising (`error_type="timeout"` on the same metric) and whether
outputs got longer (`gen_ai_client_token_usage` with `gen_ai_token_type="output"`).

**What to do.** If the provider is slow for everyone, wait or switch to the backup. If outputs
grew after a prompt change, that change made drafts longer: measure it and roll it back if needed.
Raising the timeout hides the problem and slows every failing run; do it only with a reason
recorded in ADR 0004.

## ModelCallsCutOff

**What it means.** More than 12% of model calls in the last hour stopped at the output token limit
(finish reason `max_tokens`), over at least 10 runs. A cut-off draft is invalid and needs a
second, full attempt, so runs get slower, dearer and fail more. Evaluations cut off about 5% of
draft calls.

**How to check.** `sum by (gen_ai_response_model) (increase(gen_ai_client_operation_duration_seconds_count{scopesteps_finish_reason="max_tokens"}[1h]))`.
Compare the sent limit (`gen_ai.request.max_tokens` on the spans) with the output tokens used.
Long sources or many sources in one run produce long drafts.

**What to do.** If one prompt version or model is the cause, roll it back. If the provider lowered
its per-request limit, update its profile (`infrastructure/providers/<name>.py`) and record it.
Raising `RUN_MAX_OUTPUT_TOKENS` is a budget change: check it against the provider's limit first.

## AgentRunCostHigh

**What it means.** The mean estimated cost of one run kind over the last 6 hours is more than
twice its evaluation mean, over at least 10 runs of that kind: drafts above $0.047, change runs
above $0.014, replies above $0.0026. The `scopesteps_run_kind` label says which.

**How to check.** Mean cost by prompt and model:
`sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_run_cost_USD_sum{scopesteps_run_kind="draft"}[6h])) / sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_run_cost_USD_count{scopesteps_run_kind="draft"}[6h]))`.
More calls per run (repairs, retries, clarification rounds) or more tokens per call raise it; so
does a new price in `domain/pricing.py`.

**What to do.** Costs are estimates at paid rates; on the free tier nothing is billed, but the
same runs would cost this much on a paid plan. Find what grew (calls, tokens or price) and fix
that cause. The per-run and per-project cost limits in settings still stop any single run.

## AgentRunProblemsHigh

**What it means.** Drafts or change sets leave more check problems after their one repair than in
evaluation, over at least 10 runs in 6 hours: drafts above 5.7 problems on average, change runs
above 0.5. Reviewers get drafts with more unresolved citations, quotes or coverage gaps.

**How to check.** The problem codes are on each `agent_run` span
(`scopesteps.run.problem_codes`); in Tempo, `{name="agent_run draft"}` and sort by
`scopesteps.run.problems`. A single code dominating points at one check or one source.

**What to do.** If it started with a new prompt, model or check, roll it back and measure it.
If one project's sources cause it (very long or unusual documents), that is a dataset gap: add a
synthetic pack like it to the dev packs.

## BackupCircuitOpened

**What it means.** The primary model failed for availability (overload, timeout or quota) 3
times within 2 minutes, so the circuit breaker opened and new runs start on the backup provider
for 5 minutes (ADR 0006). Runs still work, on a different model with its own data terms and
scores.

**How to check.** Primary errors by type:
`sum by (error_type) (increase(gen_ai_client_operation_duration_seconds_count{error_type!=""}[15m]))`.
Runs on the backup have `scopesteps_run_served_by="backup"`. The API log says when the circuit
opened, went half-open and closed.

**What to do.** Usually nothing: it closes by itself once the primary answers again. If it keeps
reopening, the primary has an outage or its quota is spent; check the provider. Scores are per
model, so results from runs on the backup are not comparable with the primary's evaluations.

## Adding a notification channel

Notifications stay local in the POC: Alertmanager's only receiver emails Mailpit. To notify
people later, edit [ops/monitoring/alertmanager.yaml](../../ops/monitoring/alertmanager.yaml):

1. Add a receiver with the integration you need (`email_configs` with a real SMTP server,
   `slack_configs`, `webhook_configs`, `pagerduty_configs`, `msteamsv2_configs` and others; see
   the [Alertmanager configuration reference](https://prometheus.io/docs/alerting/latest/configuration/#receiver)).
2. Route to it, for example `critical` alerts only:
   `routes: [{matchers: ['severity="critical"'], receiver: on-call}]` under `route`.
3. Keep secrets out of the file: use the integration's `*_file` setting (such as
   `api_url_file` or `auth_password_file`) pointing at a mounted secret, never a value in git.
4. Run `just alerts-check`, restart Alertmanager (`docker compose restart alertmanager`) and
   send a test alert with `amtool alert add` or by lowering a threshold locally.

A hosted backend (Grafana Cloud, a cloud's managed Prometheus) can load the same
`alerts.yaml` unchanged; its own Alertmanager then takes the receivers.

## Changing a threshold

Thresholds are reviewed whenever a prompt is adopted (evals/README.md, "Alert thresholds"):

1. `just evals-baselines <stamp>...` with the new prompt's dev report, and the reports kept for
   the other run kinds.
2. Update the table in evals/README.md, the threshold, `threshold` and `source` in
   `alerts.yaml`, and the expected annotations in `alerts.test.yaml`.
3. `just alerts-check`, then restart the backend (`docker compose restart otel`).

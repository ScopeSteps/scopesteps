# Agent alerts runbook

What each agent alert means, how to check it and what to do. The rules are in
[ops/monitoring/alerts.yaml](../../ops/monitoring/alerts.yaml)
([ADR 0023](../adr/0023-alert-rules-as-code-from-evaluation-results.md)); each threshold comes from
a recorded evaluation (evals/README.md, "Alert thresholds") or, where no Claude evaluation has
measured it yet, from [ADR 0032](../adr/0032-claude-models-through-per-step-profiles.md). Until the
first Claude dev-pack reports are in, the cost and latency thresholds are provisional.

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
runs, one bad run is not a trend. A rule that fires has also held for 5 minutes. The spend-limit
rule is the exception to both: one refused call fires it at once. Severity is `critical` (runs are failing for people) or `warning` (worse or dearer
than evaluated, but working).

## Checking an alert

For any alert, these help:

- **Prometheus** (http://localhost:9090): paste the rule's expression from `alerts.yaml` and
  drop the threshold to see the current value. Group by a label to find the cause, for example
  `sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_runs_total{scopesteps_run_status="failed"}[1h]))`.
  Model-call metrics also carry `scopesteps_step` and `scopesteps_model_profile_id`.
- **Tempo** in Grafana Explore: `{name=~"agent_run.*" && status=error}` lists failed runs with
  their `error.type`; `{name=~"chat.*"}` lists model calls with duration and finish reason.
- **The API log**: run and call events carry the same ids and codes, never content. A call event
  carries `scopesteps.provider_request_id`, the id Anthropic support asks for.
- **What changed**: a new prompt version, profile, model or price shows up as a new
  `scopesteps_prompt_version`, `scopesteps_model_profile_id` or `scopesteps_run_model` label
  value.

## AgentRunFailureRateHigh

**What it means.** More than 10% of agent runs that finished in the last hour failed, over at
least 10 runs. Evaluations fail about 1 run in 50. People get an error instead of a draft, a
change set or a reply.

**How to check.** Find the error codes:
`sum by (error_type, scopesteps_run_kind) (increase(scopesteps_agent_runs_total{scopesteps_run_status="failed", scopesteps_replay="false"}[1h]))`.

- `MODEL_TIMEOUT`, `MODEL_UNAVAILABLE`, `MODEL_QUOTA`: Claude is slow, overloaded or rate
  limited. See ModelCallLatencyHigh and the Anthropic status page. A spend limit has its own
  alert, ModelSpendLimitReached.
- `INVALID_MODEL_OUTPUT`: the model's answers no longer pass the output schema, often because
  they were cut off (see ModelCallsCutOff). Look for a new prompt version or model in the labels.
- `RUN_BUDGET_EXCEEDED`: runs hit the turn, token or cost limits in settings; see AgentRunCostHigh.

**What to do.** For a provider outage, wait it out: there is no backup provider (ADR 0032), and
failed runs can be started again. For output errors after a change,
roll back the prompt or model and measure it with the evaluations before trying again. Never raise
the threshold to quiet the alert.

## ModelCallLatencyHigh

**What it means.** For one step (the `scopesteps_step` label), the 95th percentile model call
over the last 15 minutes took more than half that step's timeout, over at least 5 runs: outline
210 s, change 120 s, explore and change_explore 90 s, epic_stories and suggest_tasks 60 s, reply
30 s. The timeouts are the `claude-mix-v1` profile's (ADR 0032); a call that reaches its step's
timeout fails, so runs are getting close to failing. No Claude evaluation has measured latency
yet, so these limits are provisional.

**How to check.** Split the latency by step and model:
`histogram_quantile(0.95, sum by (le, scopesteps_step, gen_ai_response_model) (rate(gen_ai_client_operation_duration_seconds_bucket[15m])))`.
Check whether timeouts are rising (`error_type="timeout"` on the same metric) and whether
outputs got longer (`gen_ai_client_token_usage` with `gen_ai_token_type="output"`). The effort
each call ran at is on its span (`scopesteps.effort`).

**What to do.** If Claude is slow for everyone, wait. If outputs grew after a prompt or profile
change, that change made the step longer: measure it and roll it back if needed. A new timeout or
effort is a new profile (ADR 0032), never an edit to the one in use.

## ModelCallsCutOff

**What it means.** More than 12% of model calls in the last hour stopped at the output token limit
(finish reason `max_tokens`), over at least 10 runs. A cut-off draft is invalid and needs a
second, full attempt, so runs get slower, dearer and fail more. Evaluations cut off about 5% of
draft calls.

**How to check.** `sum by (gen_ai_response_model) (increase(gen_ai_client_operation_duration_seconds_count{scopesteps_finish_reason="max_tokens"}[1h]))`.
Compare the sent limit (`gen_ai.request.max_tokens` on the spans) with the output tokens used.
Long sources or many sources in one run produce long drafts.

**What to do.** If one prompt version or model is the cause, roll it back. A step's output limit
is in its profile binding (ADR 0032): raising it means a new profile, measured before use.

## AgentRunCostHigh

**What it means.** The mean estimated cost of one run kind over the last 6 hours is more than
twice its estimated mean, over at least 10 runs of that kind: drafts above $0.21, change runs
above $0.077, replies above $0.0008. The `scopesteps_run_kind` label says which. The means are
provisional: earlier evaluation runs' tokens priced at Claude rates (evals/README.md, "Alert
thresholds"), until Claude dev-pack reports replace them.

**How to check.** Mean cost by prompt and model:
`sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_run_cost_USD_sum{scopesteps_run_kind="draft"}[6h])) / sum by (scopesteps_prompt_version, scopesteps_run_model) (increase(scopesteps_agent_run_cost_USD_count{scopesteps_run_kind="draft"}[6h]))`.
More calls per run (repairs, retries, clarification rounds), more tokens per call, more thinking
(`scopesteps.usage.thinking_tokens`), fewer cache reads
(`gen_ai.usage.cache_read.input_tokens` on the spans) or a new price in `domain/pricing.py`
raise it.

**What to do.** Every Claude call is billed. Find what grew (calls, tokens, thinking, cache
misses or price) and fix that cause. The per-run and per-project cost limits in settings
(`RUN_COST_LIMIT_USD`, `PROJECT_COST_LIMIT_USD`) still stop any single run or project.

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

## ModelSpendLimitReached

**What it means.** At least one model call in the last 15 minutes was refused because the Claude
account reached its spend limit (error kind `spend_limit`). Every later call fails the same way:
runs fail at once and are not retried (ADR 0032). Severity is `critical`.

**How to check.** The refused calls by step:
`sum by (scopesteps_step) (increase(gen_ai_client_operation_duration_seconds_count{error_type="spend_limit"}[15m]))`.
The Claude Console's usage and limits pages show the limit and what spent it. Check
AgentRunCostHigh too: runs costing more than they should reach the limit sooner.

**What to do.** If the spending is expected, raise the limit in the Claude Console; failed runs
can then be started again. If not, find what spent it first (cost by run kind and prompt, see
AgentRunCostHigh), and keep the limit until that is fixed.

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

Thresholds are reviewed whenever a prompt is adopted or the model profile changes (evals/README.md,
"Alert thresholds"):

1. `just evals-baselines <stamp>...` with the new prompt's dev report, and the reports kept for
   the other run kinds.
2. Update the table in evals/README.md, the threshold, `threshold` and `source` in
   `alerts.yaml`, and the expected annotations in `alerts.test.yaml`.
3. `just alerts-check`, then restart the backend (`docker compose restart otel`).

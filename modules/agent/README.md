# scopesteps-agent

Agent harness: model providers, drafting, draft checks, budgets, tracing and cost estimates, and
durable agent runs with tools and clarification ([ADR 0005](../../docs/adr/0005-durable-agent-runs.md)).

How to change it safely: the `agent-harness` skill in `.claude/skills/` and
[ADR 0004](../../docs/adr/0004-model-provider.md). Quality is measured in
[evals/](../../evals/README.md).

## Public interface

Other modules and `evals` import only `scopesteps.agent.client`: `create_model_provider`,
`draft_single_pass`, `check_draft`, the draft schemas and version constants, `trace_scope`,
`estimate_cost_usd`, `AgentRuntime` and `RunLimits`. Everything else is internal and enforced by import-linter.

## What is where

| Path                                            | Contains                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| `domain/model.py`                               | Provider-neutral requests, results, tool calls, usage and `ModelProviderError` |
| `domain/budget.py`                              | Run limits and counters; `check_can_call` before every model call              |
| `domain/pricing.py`                             | Paid-tier price table and cost estimates (thinking billed as output)           |
| `domain/providers.py`                           | `ProviderProfile`: per-provider defaults, free-tier limits, quirks             |
| `domain/rate.py`                                | `TokenWindow`: pacing to a tokens-per-minute allowance                         |
| `domain/run.py`                                 | Run, question and step records; statuses, stages, lease                        |
| `application/ports.py`                          | The `ModelProvider` protocol: one provider, no retries, no fallback            |
| `application/schemas.py`                        | Typed draft output and tool arguments; the JSON schema sent to providers       |
| `application/drafting.py`                       | Versioned prompts and single-pass drafting with one bounded repair             |
| `application/checks.py`                         | Deterministic draft checks (citations, open decisions, story structure)        |
| `application/tracing.py`                        | `trace_scope` attributes for content-free traces                               |
| `application/runs.py`                           | Run use cases: create, get, advance (leased step), answer, cancel              |
| `application/steps.py`                          | One bounded step: an exploring call with tools, or the draft and its repair    |
| `application/fallback.py`                       | Opt-in backup at run start and the circuit breaker (ADR 0006)                  |
| `application/tools.py`                          | `lookup_source`, `request_clarification`, `validate_backlog`                   |
| `infrastructure/orm.py`                         | `agent_runs`, `agent_run_steps`, `agent_run_questions`, request receipts       |
| `infrastructure/repository.py`                  | Compare-and-set run writes, step ledger, pinned passages from `sources`        |
| `infrastructure/providers/gemini.py`            | Gemini Interactions adapter: `store=False`, SDK retries off, errors classified |
| `infrastructure/providers/openai_compatible.py` | OpenAI Chat Completions adapter (Groq, ADR 0006): no retries, strict schemas   |
| `infrastructure/providers/groq.py`              | Groq profile (backup provider)                                                 |
| `infrastructure/providers/paced.py`             | Waits for the per-minute token allowance (probes and evaluations only)         |
| `infrastructure/providers/traced.py`            | One OpenTelemetry GenAI-named event per call, success or failure               |
| `infrastructure/providers/fake.py`              | Scripted provider for tests                                                    |
| `http/`                                         | Run routes: create, get, advance, answers, cancel                              |

Tests use the fake provider or a local HTTP server; no test calls a real model. The live probe is
`just probe-model` (in `apps/api`). Run behaviour is tested end to end in
`apps/api/tests/test_runs.py`.

Tables are prefixed `agent_` (ADR 0003).

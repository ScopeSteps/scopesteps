# scopesteps-agent

Agent harness: model providers, drafting, draft checks, budgets, tracing and cost estimates. Run
state, tools and clarification persistence arrive with SSPOC-7.

How to change it safely: the `agent-harness` skill in `.claude/skills/` and
[ADR 0004](../../docs/adr/0004-model-provider.md). Quality is measured in
[evals/](../../evals/README.md).

## Public interface

Other modules and `evals` import only `scopesteps.agent.client`: `create_model_provider`,
`draft_single_pass`, `check_draft`, the draft schemas and version constants, `trace_scope` and
`estimate_cost_usd`. Everything else is internal and enforced by import-linter.

## What is where

| Path                                 | Contains                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------ |
| `domain/model.py`                    | Provider-neutral requests, results, tool calls, usage and `ModelProviderError` |
| `domain/budget.py`                   | Run limits and counters; `check_can_call` before every model call              |
| `domain/pricing.py`                  | Paid-tier price table and cost estimates (thinking billed as output)           |
| `application/ports.py`               | The `ModelProvider` protocol: one provider, no retries, no fallback            |
| `application/schemas.py`             | Typed draft output and tool arguments; the JSON schema sent to providers       |
| `application/drafting.py`            | Versioned prompts and single-pass drafting with one bounded repair             |
| `application/checks.py`              | Deterministic draft checks (citations, open decisions, story structure)        |
| `application/tracing.py`             | `trace_scope` attributes for content-free traces                               |
| `infrastructure/providers/gemini.py` | Gemini Interactions adapter: `store=False`, SDK retries off, errors classified |
| `infrastructure/providers/traced.py` | One OpenTelemetry GenAI-named event per call, success or failure               |
| `infrastructure/providers/fake.py`   | Scripted provider for tests                                                    |
| `http/`                              | Run routes (`501 NOT_IMPLEMENTED` until SSPOC-7)                               |

Tests use the fake provider or a local HTTP server; no test calls a real model. The live probe is
`just probe-model` (in `apps/api`).

Tables will be prefixed `agent_` (ADR 0003).

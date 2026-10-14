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
| `application/checks.py`                         | Deterministic draft checks (citations, open decisions, stories, people)        |
| `application/candidate.py`                      | A checked draft becomes the `backlog` candidate and the `projects` people      |
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

Runs draft with prompt `draft-v6` (schema `draft-backlog.v4`): `draft-v4`, where each question
names the stories it blocks, plus the people the sources name. `draft-v6` has not been measured
live yet (see [evals/README.md](../../evals/README.md)); `draft-v1` to `draft-v4` stay available
with the schemas and checks they were measured with. There is no `draft-v5`: that name belongs to
an experiment that was measured and not adopted.

When a draft is ready, the same transaction that marks the run `ready_for_review` saves its
candidate through `backlog.client` and hands its people to `projects.client`; a candidate the
backlog module refuses fails the run with `CANDIDATE_REFUSED` and saves neither. `candidate.py`
applies what a prompt cannot guarantee: an unresolvable citation is dropped (so the claim becomes
proposed), a skipped question stays an open decision even if the draft does not raise it again, a
criterion that quotes a disputed value is withheld and its story blocked, and a story that
implements excluded work is blocked.

## People

A `draft-backlog.v4` draft lists each person the sources name: `ref` (P1...), `name`, `role`,
`said` (one sentence in the model's words), `citations`, `rights` (`decides`, `advises` or
`not_stated`) and `rights_citations`. The model only reports a right a source states; it never
decides who has one, and confirming a right is a person's action in `projects`.

| Check code                      | Fails when                                                    |
| ------------------------------- | ------------------------------------------------------------- |
| `person_without_citation`       | A person has no citation                                      |
| `person_not_named`              | No block the person cites contains their name                 |
| `stated_right_without_citation` | `rights` is `decides` or `advises` with no `rights_citations` |

People citations also go through `unknown_block` and `quote_not_verbatim`, and requests restrict
them to the request's block ids. Any of these triggers the one targeted repair, whose patch may
replace a person by `ref`. What is stored is decided in code (`to_people`), whatever the draft or
its remaining problems say: a person is kept only when a pinned source paragraph they cite
contains their name, a stated right only with a quote that resolves (otherwise `not_stated`),
reviewer answers do not count as sources about people, and names, roles, summaries, quotes and
the number of people are cut to the limits `projects.client` publishes.

The people section's size limits are sent to the provider but not enforced by validation, so an
over-long entry cannot invalidate a whole draft. Its schema is kept small because every draft
request must fit the backup provider's per-request allowance (ADR 0006 notes).

Run actions are recorded in the project's activity log through `audit.client`, in the transaction
that stores them: `run.started`, `run.cancelled`, `clarification.answered` and
`clarification.skipped` for the reviewer, `clarification.requested` for the agent. A replayed
request and a discarded step record nothing, and no event holds a question or an answer.

Tests use the fake provider or a local HTTP server; no test calls a real model. The live probe is
`just probe-model` (in `apps/api`). Run behaviour is tested end to end in
`apps/api/tests/test_runs.py`, from clarification to the saved backlog in
`apps/api/tests/test_backlog_candidates.py`, and from a run to the stored people in
`apps/api/tests/test_people.py`.

Tables are prefixed `agent_` (ADR 0003).

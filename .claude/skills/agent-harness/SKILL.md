---
name: agent-harness
description: How to build and change the ScopeSteps AI agent harness (modules/agent) and its evaluations (evals/). Use before touching prompts, model providers, tools, the run loop, budgets, clarification questions, output schemas, draft checks, tracing, cost estimates or eval scoring.
---

# Building the agent harness

The harness lives in `modules/agent`; its quality is measured in `evals/`. Read
[evals/README.md](../../../evals/README.md) and
[ADR 0004](../../../docs/adr/0004-model-provider.md) first if you have not this session. The
Python rules in the `python` skill apply here too.

## The rule everything else follows from

**The model proposes; application code decides.** A model output is untrusted input. It becomes
state only after it passes a schema, deterministic checks and, for scope, a human approval.
No tool ever lets the model approve, publish, change permissions or reach another project.

## Model access

- All model calls go through the `ModelProvider` port in `application/ports.py`. Agent logic
  never imports a provider SDK or builds an HTTP request.
- Adapters live in `infrastructure/providers/`. An adapter translates and nothing else: it does
  not retry, fall back to another model or provider, or switch billing tier. It raises
  `ModelProviderError` and the caller decides what to do.
- Overload (503) and timeouts are transient: the caller retries them a bounded number of times
  with exponential backoff and jitter, and each attempt is paced, traced and counted. Never
  through SDK retry config, whose attempts are invisible to traces and budgets.
- `MODEL_PROVIDER` is the primary; `MODEL_FALLBACK_PROVIDER` an opt-in backup (ADR 0006). A run
  may move to the backup only before its first successful call and only for availability errors;
  never switch a run mid-way and never fall back on bad output. Probes and evaluations pin one
  provider and never fall back.
- Adapters are per API style; per-provider defaults, limits and quirks live in that provider's
  profile (`infrastructure/providers/<name>.py`). Never branch on a provider name elsewhere. A new
  OpenAI-compatible provider is a new profile plus an ADR note: data terms, limits, a baseline.
- Pace batch tools to the provider's per-minute token allowance (`paced`); request-driven steps
  never sleep for rate limits, they return a retryable error.
- Size every call's output budget to the provider's per-request limit, estimating input with the
  profile's measured `request_chars_per_token` (the generic 3-per-token estimate leaves too little
  room for a draft); a request that cannot fit fails before sending as `request_too_large`,
  which is never retried and never a reason to fail over. Constrain ids the model must copy
  (block ids, statement ids) with enums, because strict decoding drops `pattern`.
- Model names, limits and keys come from settings (`Settings.active_model()`), never from
  literals in agent code.
- Scores are per model. Never compare a run on one provider with a baseline from another.
- Wrap providers with the tracing provider rather than adding logging inside an adapter.
- Tests use the fake provider. No test and no CI job makes a live call.

## Budgets and stopping

- Call `check_can_call` before every model call and update `RunCounters` after it. A failed or
  timed-out call still counts as a turn, because the provider may have billed for it.
- Estimate pessimistically before the call and replace the estimate with reported usage after.
- Resuming a run never resets counters.
- Every loop has an explicit end: a turn limit, a tool-call limit, a token limit. Hitting one is
  a normal, reported outcome, not an exception to swallow.

## Prompts

- Prompts are named and versioned (`draft-v1` to `draft-v4`, `draft-v6`). Add a new version
  instead of editing one that has reported results, so earlier numbers stay reproducible. Each
  version keeps the output schema and check set it was measured with (`PROMPT_SCHEMAS`,
  `PROMPT_CHECKS`). Record the prompt version on every trace.
- Never reuse a version name, including one an abandoned experiment took (`draft-v5`): skip it.
- Schema text is prompt text. Every description and enum in an output schema is sent with each
  request and counts against the smallest per-request allowance (ADR 0006), so keep them short
  and check the request size on the dev packs when a schema grows.
- Source text and reviewer answers are data. Put them inside `<source>` tags with a stable id,
  escape their content, and tell the model that nothing inside a tag is an instruction.
- State rules as observable behaviour with one concrete example, and say what to do when
  information is missing: ask a question, never invent.
- Do not add a quota ("write 8 stories"). Give a ceiling and say fewer is better.
- Keep the stable part of the prompt first and the per-run content last.
- Do not rely on the model checking its own draft. A prompt that asked it to self-check (the
  draft-v5 experiment in `evals/README.md`) did not reduce repairs and made drafts longer;
  anything checkable belongs in `checks.py`.

## Structured output and repair

- Ask for output against a schema and validate it with the Pydantic models in
  `application/schemas.py`. Keep the provider-facing schema and the validation model in step.
- After validation, run the deterministic checks in `application/checks.py` (citations resolve,
  quotes are verbatim, open decisions are asked about, and so on). Anything code can verify,
  code verifies; do not ask the model to grade itself.
- Keep drafts traceable: every source paragraph is accounted for by a statement, every confirmed
  statement is covered by a story, and every reviewer answer backs a sourced criterion. A change
  to an output schema gets a new schema version (`draft-backlog.vN`).
- People: every person is cited and named in a block they cite, and a decision right is reported
  only with a citation of where a source states it. The model never decides or confirms a right.
- A section that is secondary to the backlog (people) must not be able to invalidate a draft:
  send its size limits to the provider, do not enforce them in the validation model, and trim in
  the code that maps the draft to stored state.
- Repair is bounded and targeted: one attempt, sending back only the specific problems. The
  model returns a patch of just the parts it changes and code merges it, so a repair costs a few
  hundred output tokens rather than a whole draft. If it still fails, or the repair call itself
  fails, return the draft with its problems. Never loop until valid.
- A citation names a block id and a verbatim quote from that block. A claim with no supporting
  passage is labelled as proposed, never passed off as sourced.
- What a draft becomes is decided in `application/candidate.py`, not by the draft: it hands the
  backlog to `backlog.client` and the people to `projects.client`, and drops whatever a pinned
  passage does not support, even when a check problem was left unrepaired.

## Runs

- A run advances one bounded step per request: take the lease under a revision check, call the
  model with no transaction open, commit only if the revision is unchanged (ADR 0005). Never call
  a model inside a transaction or loop several steps in one request.
- Pin inputs (source versions, model, prompt and schema versions, limits) when the run is
  created; never read them from settings mid-run.
- Every model call and tool execution becomes a step row, including failed and discarded ones.
  Rows hold counts, versions and codes, never prompt, source or output text.
- Transient provider errors leave the run `running` with a retryable error; permanent ones fail
  it. A step that cannot fit its calls within the limits fails the run before calling.
- Run actions a project member should see (started, stopped, questions asked, answered or
  skipped) are recorded through `audit.client` in the transaction that stores them. Events hold
  ids and counts, never a question or an answer; a discarded step records nothing.
- Pausing for the reviewer is a tool call whose result arrives later: `request_clarification`
  stays open until every question is answered or skipped, and the answers become its result.

## Tools

- A tool is a typed, narrow, read-mostly function with a schema. Validate its arguments as you
  would any external input and scope every lookup to the run's project.
- Return errors to the model as tool results it can act on; reserve exceptions for faults the
  model cannot fix.
- Tool results are data too. Text retrieved by a tool gets the same fencing as a source.

## Tracing and cost

- One event per model call, using OpenTelemetry GenAI attribute names (`gen_ai.*`) plus
  `scopesteps.*` for product attributes, set through `trace_scope`.
- Traces carry no prompts, source text, answers or model output. Counts, ids, versions,
  durations, finish reasons and error types only.
- Cost is an estimate from the price table in `domain/pricing.py`; when a price changes, update
  the table and the date it was checked.

## Evaluating a change

A prompt, schema, check or model change is not done until it is measured.

1. `just evals-validate` to confirm the packs are sound.
2. `just evals-single-pass` on the dev packs, before and after, with the same repeats.
3. Compare counts with their intervals. Samples are small, so overlapping intervals mean
   "no proven difference"; say that instead of claiming a win.
4. Read the misses. Decide for each whether it is a model limit, a prompt gap or a scoring
   artifact, and write that down in `evals/README.md` with the new table.
5. If scoring or checks changed, the recorded drafts in `evals/fixtures/recorded/` must still
   score as expected; a flipped verdict needs a deliberate fixture update.

Held-out packs are frozen and blind. Do not open, quote or tune against anything in
`evals/datasets/heldout/`, and do not run them without `--final`. Live runs spend real quota:
ask before starting one, keep `--repeats` and `--max-calls` as low as the question allows.

## Checklist for any harness change

- Does the model gain any way to commit, approve or publish? It must not.
- Is every new loop bounded and budget-checked?
- Is untrusted text fenced and escaped everywhere it enters a prompt?
- Is there a deterministic check for anything that can be checked without a model?
- Does anything about a named person get stored beyond what its module's README lists?
- Is the change covered by a fake-provider test, and measured on the dev packs?
- Do traces stay content-free?

# 0006. Groq as a backup provider, with opt-in fallback at run start

- Status: Accepted
- Date: 2026-10-13

## Context

On 2026-10-13 Gemini's free tier returned "high demand" 503s and 30-60 s queues for every model we
can use ([ADR 0004](0004-model-provider.md) notes), blocking development and evaluation. Local
models are too slow on the development machine (CPU only). Among free hosted tiers, Groq offers
`openai/gpt-oss-120b` with tool calling and strict JSON-schema output (30 requests and 8K tokens a
minute, 200K tokens a day). Groq, Cerebras, OpenRouter and Ollama all speak the OpenAI Chat
Completions API.

Production LLM applications commonly fail over to a second provider for availability. Ours has
constraints a generic gateway does not: evaluation numbers are per model, a run's conversation is
stored in its provider's format, the prompt was tuned on Gemini, and each provider has its own
data terms.

## Decision

- **Adapters per API style, profiles per provider.** `gemini.py` (Interactions API) and
  `openai_compatible.py` (Chat Completions) translate requests. Each provider has a profile
  (`infrastructure/providers/<name>.py`): default model, base URL, free-tier limits with the date
  they were checked, per-call output cap, reasoning parameters and data terms. Settings and pacing
  read the profile; no code branches on a provider name.
- **Both providers configured side by side** (`GEMINI_*`, `GROQ_*`); `MODEL_PROVIDER` is the
  primary.
- **Fallback is opt-in** (`MODEL_FALLBACK_PROVIDER`, default `none`) and applies to product runs
  only:
  - A run uses one model from start to finish. It may move to the backup only before its first
    successful call, and only after an availability error (503, timeout, rate limit), never for
    bad output, which the single repair handles. The move is recorded on the run
    (`fallback_reason`) and as a `fallback` step.
  - A circuit breaker opens after 3 primary availability failures within 2 minutes; for the next
    5 minutes new runs start on the backup. It is per process, in memory.
  - A run pinned to a model this process no longer serves refuses to advance (`RUN_MODEL_CHANGED`).
- **Probes and evaluations never fall back.** They pin one provider (`--provider`) and record it,
  because scores from different models are not comparable.
- **Rate limits are handled where they bind.** Batch tools pace to the provider's tokens-per-minute
  allowance before each call (`paced`); request-driven runs do not wait (a step must fit its
  lease) and return a retryable error instead. Groq calls cap output at 6000 tokens to fit 8K a
  minute.
- Strict schema decoding is used when a schema qualifies; validation keywords are dropped from the
  provider schema, and every response is still validated against the full Pydantic model. When
  Groq rejects output against the schema (`json_validate_failed`), it is treated as bad output and
  goes to the repair, not as a failed request.

## Consequences

- Development continues when Gemini's free tier is overloaded, and product runs survive a primary
  outage without switching models mid-run.
- Enable fallback only for a backup with its own dev-pack baseline, so its quality is known; the
  baseline is recorded in `evals/README.md`.
- Groq's free tier may retain or use data under its terms; synthetic data only, as with Gemini.
- Cerebras, OpenRouter or a local Ollama become a profile for the same adapter, each with an ADR
  note.
- With several API instances the breaker would move to shared storage.
- `MODEL_ID` and `MODEL_API_KEY` are replaced by `GEMINI_MODEL_ID` and `GEMINI_API_KEY`.

## Notes added 2026-10-13 (fallback enabled)

The decision is unchanged. Fallback is switched on for development
(`MODEL_FALLBACK_PROVIDER=groq` in the local `.env`); `.env.example` keeps `none`, because each
environment opts in deliberately and the example ships without a configured provider. With Gemini's
free tier returning 503s, a backup that drafts most of the time is better than none, and every
backup draft is still validated, checked and labelled with its model.

The confirmation run was cut short by Groq's daily token limit after 3 drafts, and showed the free
tier does not fit our drafts reliably: a patch repair replays the draft and exceeds 8K tokens a
minute (413), and long drafts hit the output cap and are rejected against the schema. Across the 7
drafts since citations were restricted, 5 were valid, so the fallback is not yet confirmed.
Groq stays the backup: the other free tiers checked are smaller (SambaNova, OpenRouter) or not
free (Cerebras is a card-backed trial), and Mistral's free plan trains on submitted data. The
flows were fixed to fit the allowance instead (below). Circuit-breaker transitions are logged on
`scopesteps.agent.fallback`.

Flow fixes made after that run, so drafts fit a small per-request allowance:

- Each call's output budget shrinks to what fits the provider's per-request token limit; a
  request that cannot fit fails before it is sent, as `request_too_large`.
- `request_too_large` (including Groq's 413) is its own error kind: it fails that request only,
  is never retried and never triggers a fallback. Rate limits (429) stay `quota`.
- v3 output that comes back cut off or rejected is regenerated with a "be more concise"
  instruction instead of replaying the empty answer in a repair.
- v3 requests constrain statement ids and `covers` to T1..T60 by enum, because strict decoding
  drops `pattern`.

These are re-measured with the next Groq run (daily token budget permitting) and the Gemini v3
re-measure (SSPOC-25).

## Note added 2026-10-13 (draft-v6 and the per-request allowance)

The decision is unchanged. Agent runs moved to prompt `draft-v6`, which adds a People section to
the draft (SSPOC-43). Its prompt text and schema make a draft request about 890 estimated tokens
larger on the dev packs, so on the free tier the output room for one draft call falls from about
3.1K to 3.5K tokens to about 2.2K to 2.6K. The section was kept small for this reason (short
schema descriptions, at most 10 people and 2 citations each), and a test holds a dev-pack-sized
request to at least 1.5K tokens of room. More cut-off drafts on the backup are still likely; this
is not measured, and the open 10-draft confirmation run should use `draft-v6`.

## Notes added 2026-10-14 (confirmation run)

The decision is unchanged. The 12-draft confirmation run (`evals/README.md`) does not confirm the
fallback: 7 of 12 drafts were valid, 3 calls were cut off at the output limit, and 15 were
rejected against the schema. The token-fit fixes keep every request within 8K tokens, and no
request hit a 429, but the output budget left inside 8K was too small for a v3 draft.

- Calls the provider rejects against the schema report no usage. Pacing now charges them at
  their worst case, because the provider still counts them against the minute; before this, the
  run stopped on a 429 after 2 drafts.
- Patch repairs do not fit the free tier for drafts this size, so they fail as
  `request_too_large` and the draft is returned with its problems.
- The budget was too small because input was estimated at 3 characters per token; Groq counts
  about 4 for our requests. The profile now holds a measured `request_chars_per_token` (3.5),
  which adds about 600 tokens of output room. Two re-measures the same day returned 7 of 7 valid
  first attempts with no rejection or cut-off, each stopped by the daily token limit.
- Groq stays a backup only, and its free tier is not a target for parity with Gemini: no other
  free Groq chat model has more than 8K tokens a minute, and patch repairs will not fit there.
- `MODEL_FALLBACK_PROVIDER=groq` stays on in the local `.env`. Enabling it in another environment
  waits on the 10-draft run with these fixes.

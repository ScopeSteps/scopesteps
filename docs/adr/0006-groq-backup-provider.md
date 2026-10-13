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

The decision is unchanged. Fallback is now switched on for development
(`MODEL_FALLBACK_PROVIDER=groq` in the local `.env`); `.env.example` keeps `none`, because each
environment opts in deliberately and the example ships without a configured provider. Evidence:
the 4-draft Groq baseline with restricted citations (`evals/README.md`) and Gemini's free tier
returning 503s for most of the day. A 10-draft Groq run confirms it when the daily token budget
allows; if it falls short, set the variable back to `none`. Circuit-breaker transitions are
logged on `scopesteps.agent.fallback`.

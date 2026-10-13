# 0006. Groq as a manually selected backup provider

- Status: Accepted
- Date: 2026-10-13

## Context

On 2026-10-13 Gemini's free tier returned "high demand" 503s and 30-60 s queues for every model we
can use ([ADR 0004](0004-model-provider.md) notes), blocking development and evaluation. Local
models are too slow on the development machine (CPU only). Among free hosted tiers, Groq offers
`openai/gpt-oss-120b` with tool calling and strict JSON-schema output, 30 requests and 8K tokens a
minute, and 200K tokens a day. Groq, Cerebras, OpenRouter and Ollama all speak the OpenAI Chat
Completions API.

## Decision

- Add one adapter for the OpenAI Chat Completions API behind the existing `ModelProvider` port,
  with Groq (`openai/gpt-oss-120b`) as its first configuration. The adapter sends no SDK retries,
  does not request or store reasoning text, and classifies errors like the Gemini adapter.
- Gemini stays the primary provider. Groq is a backup selected by editing `MODEL_PROVIDER`.
  There is still no automatic fallback: one provider per process, as ADR 0004 requires.
- Each provider has its own key and model settings (`GEMINI_*`, `GROQ_*`), so both can be
  configured at once. A run pins its provider and model, and refuses to advance on another.
- Groq calls cap output at `GROQ_MAX_OUTPUT_TOKENS` (6000) to fit the free per-minute token
  allowance, and evaluations pace Groq at one call a minute by default.
- Strict schema decoding is used when a schema qualifies (every property required, no extra
  properties); validation keywords are dropped from the provider schema, and every response is
  still validated against the full Pydantic model.

## Consequences

- Development and evaluation can continue when Gemini's free tier is overloaded.
- Results from different models are not comparable. Each model needs its own baseline, and
  reports record the provider and model.
- Groq's free tier may retain or use data under its terms; synthetic data only, as with Gemini.
- Cerebras, OpenRouter or a local Ollama can be added later as configuration of the same adapter,
  each with an explicit decision.
- `MODEL_ID` and `MODEL_API_KEY` are replaced by `GEMINI_MODEL_ID` and `GEMINI_API_KEY`.

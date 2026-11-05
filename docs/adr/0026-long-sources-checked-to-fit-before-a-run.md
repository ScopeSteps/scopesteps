# 0026. Long sources, sent whole and checked to fit before a run starts

- Status: Accepted
- Date: 2026-11-04

## Context

A project's current sources could hold 6,000 words together (`SOURCE_MAX_WORDS`,
[ADR 0009](0009-sources-of-any-kind-and-soft-removal.md)). One real one-hour meeting is about
8,000 to 9,000 words, so real projects did not fit. Decided 2026-11-03 (Sara): raise the limit so
a project can hold several meetings and documents, proposed at 60,000 words, and keep checking
before every model call that its input fits the model and the cost limits.

Every model call of a run sends every pinned source: the agent reads sources, it does not search
them. At 60,000 words a call carries about 140,000 estimated tokens (the pessimistic
3-characters-per-token estimate), so the run's old 200,000-token limit
([ADR 0004](0004-model-provider.md)) would stop a run after its first call, and an explore step
could use up the room a draft needs.

## Decision

- **Projects hold up to 60,000 words** by default (`SOURCE_MAX_WORDS`), and a run may use up to
  600,000 tokens (`RUN_MAX_TOTAL_TOKENS`): enough at the limit for a draft, its repair and up to
  two explore calls. Both stay configurable.
- **Sources are still sent whole.** Retrieval (sending only the passages a step needs) is out of
  scope; it would change what the agent can cite.
- **Each provider profile records the default model's request limit** (`max_input_tokens`, from
  the provider's model page). What one request may hold is that limit, or the per-minute token
  allowance when it is lower, since a larger request could never be sent.
- **A run that could not finish is refused before it starts.** Creating an initial run estimates
  a draft's input from its pinned sources and refuses with `413 RUN_INPUT_TOO_LARGE` when a
  draft and its repair would not each fit one request, or together the run's token limit. The
  message says, in words rather than tokens, how much the sources hold and how much fits. Nothing
  is stored and no model is called.
- **Every step checks the request size too**, with the turn, token and cost limits, before it
  calls the model. A change or reply run whose sources do not fit fails at its first step with
  the same code and message, having called nothing. Turn and cost limits are not checked at
  creation, because they do not depend on the sources' length.
- **Exploring yields to the draft.** An explore step runs only while the draft (or change set)
  and its repair still fit after it, so long sources go straight to drafting instead of stopping
  half done.

## Consequences

- Projects of a few real meetings fit, and a run on them either completes or is refused at the
  start with a reason people can act on.
- Long runs cost more. At the limit a draft run may send about 400,000 to 500,000 tokens: about
  $0.15 at `gemini-3.5-flash-lite`'s paid input price, before output. The cost limits
  (`RUN_COST_LIMIT_USD`, `PROJECT_COST_LIMIT_USD`) still apply before every call.
- Each call takes longer with more input, against the 30-second call timeout
  (`MODEL_TIMEOUT_SECONDS`) and the 90-second step lease.
- Gemini's model page gives a 1,048,576-token request limit, but a developer forum report says
  the Interactions API, which our adapter uses, caps one turn's input at 32,768 tokens for
  Flash-Lite. If that holds, requests of more than about 20,000 words fail there. A live run on a
  long dev pack, after asking, settles this and the timing; until then the default is the
  proposal, not a measured value.

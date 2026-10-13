# 0004. Model provider: Gemini 3.5 Flash-Lite on the free tier, behind one adapter

- Status: Accepted
- Date: 2026-10-12

## Context

The POC needs one model that returns typed output and tool calls, at no cost, with synthetic data
only (POC Implementation Plan, sections 7, 11 and 13). The Gemini API was the first candidate.

Terms checked on 2026-10-12 ([pricing](https://ai.google.dev/gemini-api/docs/pricing),
[terms](https://ai.google.dev/gemini-api/terms), last updated 2026-04-28):

- Free-tier prompts and responses may be used to improve Google's products and read by human
  reviewers. Sensitive, confidential or personal data must not be sent. Users must be 18 or older.
- Paid services are required for apps offered to users in the EEA, UK or Switzerland. The POC is
  used only in the US by a handful of users.
- Free-tier limits are per project and per model, are not published, and are shown in AI Studio.
- The Interactions API is generally available and recommended for new projects. It stores
  interactions server-side by default (1 day on the free tier).

The project is an AI Studio project with no billing account attached, so it cannot incur charges.

Probe results (`uv run scopesteps-probe-model`, reports in `evals/probes/`), campus-room-booking
dev pack:

| Model                   | Result                                                                                              |
| ----------------------- | --------------------------------------------------------------------------------------------------- |
| `gemini-3.8-flash`      | All checks passed once, but 20-90 s per call, timeouts at 60 s, then 503 and 429 after ~25 requests |
| `gemini-3.6-flash`      | 429 on the first request: no usable quota on this project                                           |
| `gemini-3.5-flash-lite` | All 5 checks passed with `minimal` and `low` thinking; 0.6-8.6 s per call; 0 citation errors        |

Measured SDK behaviour (google-genai 2.28.0): the default client retries 408/409/429/5xx up to
four times without telling the caller, and `attempts=0` still sends two requests.

## Decision

- **Model:** `gemini-3.5-flash-lite` through the Gemini Developer API, Interactions API,
  google-genai 2.28.0.
- **Configuration:** `store=False`; thinking level `minimal`; timeout 30 s; at most 8,000 output
  tokens per call; SDK retries disabled (`HttpRetryOptions(attempts=1, http_status_codes=[599])`,
  pinned by `modules/agent/tests/test_gemini_http.py`).
- **Versions recorded:** prompt `probe-v1+850337aa7a7f`, output schema `draft-backlog.v1`
  (sha256 `b06278de4d64…`). Each run and report records the model, prompt and schema versions.
- **Adapter boundary:** agent code calls only the `ModelProvider` protocol
  (`scopesteps.agent.application.ports`). `infrastructure/providers/gemini.py` is the only code
  that imports the Google SDK. Provider errors are classified (quota, unavailable, timeout, auth,
  invalid_request, blocked, malformed_response) without echoing provider bodies.
- **Limits:** six model turns, eight tool calls, 8,000 output tokens per call and 200,000 tokens
  per run, checked before every call. Failed and timed-out calls still count as turns. Resuming a
  run never resets counters. Cost limits stay unset while the project has no billing account.
- **No silent fallback:** one provider and one model per process. No automatic retry, no other
  model, no other provider and no paid tier. Changing any of these is a configuration change,
  reviewed and recorded in a new ADR.
- Citations are checked against blocks with `quote_matches`: markdown markers, typographic quotes
  and whitespace may differ, wording may not. Flash-Lite drops `**Speaker:**` markup when quoting.

## Consequences

- Calls are fast enough for interactive use, and the free tier keeps the POC at zero cost.
- Flash-Lite is the smallest model tried. Quality varies between runs (one of four drafts missed
  a clarification question), so evaluation repeats runs and reports variance.
- Free-tier capacity and latency are not guaranteed. A recorded demo is the backup, as the POC
  plan already requires.
- Synthetic data only, for as long as the free tier is used.
- Re-check quota, terms and the SDK retry test before upgrading google-genai or changing model.
- Rejected for now: `gemini-3.8-flash` (latency and quota) and `gemini-3.6-flash` (no quota).
  Paid Gemini, Claude, OpenAI and local Ollama remain options behind the same adapter, each
  needing an explicit decision about cost and data use.

## Notes added after acceptance (2026-10-12)

The decision is unchanged. Corrections and evidence gathered later the same day:

- AI Studio free-tier limits for this project: `gemini-3.5-flash-lite` 15 RPM, 250K input TPM,
  500 RPD; `gemini-3.8-flash` and `gemini-3.6-flash` 5 RPM and about 20 RPD; `gemini-2.5-flash`
  5 RPM, 20 RPD; 2.0 models and `gemini-2.5-pro` have no free quota. The 3.8-flash 429s came from
  exceeding 5 RPM and its daily cap.
- Correction: `gemini-3.6-flash` does have free quota (same limits as 3.8-flash). Its 429 was a
  limit, not an absence of quota. It is still unsuitable for the same reason as 3.8-flash.
- `gemini-2.5-flash` returns 404 on the Interactions API (it supports `generateContent` only), so
  comparing it would need a second adapter path for an older model with 20 RPD. Not pursued.
- The prompt moved to `scopesteps.agent.application.drafting` as `draft-v1+850337aa7a7f`. The text
  and hash are identical to the probed `probe-v1+850337aa7a7f`.
- First single-pass baseline on the dev packs (3 repeats per mode): 12/12 valid drafts, no repairs,
  6-8 s per draft. See the single-pass section of `evals/README.md`.
- Later prompt versions (each with its hash), their check sets and measurements are recorded in
  `evals/README.md`, not here; this ADR covers the provider decision.
- Every model call is now traced (OpenTelemetry GenAI attribute names, no content) and costed at
  paid rates from `modules/agent/src/scopesteps/agent/domain/pricing.py` (prices checked
  2026-10-12: $0.30 input and $2.50 output per million tokens for Flash-Lite).

## Notes added 2026-10-13

The decision is unchanged. Free-tier overload observed:

- `gemini-3.5-flash-lite` answered a one-word request in 30-36 s and then returned 503; a v3 run
  had 7 of 8 drafts fail on 30 s timeouts or 503. The same requests took 6-10 s on 2026-10-12.
  Google treats 503 as temporary overload, unrelated to quota, and other free-tier users reported
  the same at the time. Latency here is queueing, not generation: a 17-token tool call took 18 s.
- This is the risk the decision already accepts ("capacity and latency are not guaranteed").
  Measurements are only compared when taken in the same window.
- `gemini-3.8-flash` now returns 400 on the same request; it stays rejected and was not pursued.
- Later the same day the 503 body named the cause: "gemini-3.5-flash-lite is currently
  experiencing high demand". It came back on both `generateContent` and the Interactions API,
  while listing models with the same key took 1.4 s, so the key, network and adapter are not the
  cause. `gemini-3.8-flash` returned the same message; `gemini-3.6-flash` returned 429 (quota).
- By the evening of 2026-10-13 the free tier had recovered: `just probe-model` passed all five
  checks, and 40 dev drafts (v3 and v4, 20 each) completed with no provider failure at 11-12 s
  p50 (evals/README.md). The overload was temporary, as Google described it.

## Notes added 2026-10-13 (backup provider)

The primary decision is unchanged: Gemini, one model per run, adapters that never retry or
switch on their own. [ADR 0006](0006-groq-backup-provider.md) adds Groq as a backup and an opt-in
fallback that applies only before a run's first successful call; probes and evaluations never
fall back. `MODEL_ID` and `MODEL_API_KEY` became `GEMINI_MODEL_ID` and `GEMINI_API_KEY`.

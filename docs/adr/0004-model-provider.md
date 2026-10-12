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

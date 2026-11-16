# 0032. Claude Sonnet 5.5 and Haiku 5.5 through model profiles per step

- Status: Accepted
- Date: 2026-11-15
- Supersedes: [0004](0004-model-provider.md), [0006](0006-groq-backup-provider.md)

## Context

The agent ran on `gemini-3.5-flash-lite` on Gemini's free tier ([ADR 0004](0004-model-provider.md)),
with Groq's free tier as an opt-in backup ([ADR 0006](0006-groq-backup-provider.md)). That served the
POC, but Release 1 needs more:

- **Capacity.** The free tier's capacity and latency are not guaranteed. It returned "high demand"
  503s and 30-60 s queues for days at a time (ADR 0004 notes). Groq's 8K tokens a minute cannot
  hold a draft and its repair, and since ADR 0006's 2026-11-12 note it is never used for runs on
  real sources.
- **Quality.** Flash-Lite is the smallest model we tried, and its drafts vary between runs.
  Release 1 asks for a stronger model.
- **Data terms.** The free tier may use prompts and responses to improve Google's products. That
  limited us to synthetic data, and it could never be offered to the EEA, the UK or Switzerland.
- **Shape of the work.** Since [ADR 0028](0028-drafting-in-steps-without-the-size-cap.md), a run makes
  several kinds of call. The outline and the change set need the strongest reasoning. Epic
  stories, replies and task suggestions are short and frequent. One model per run pays the
  strong model's price for every call, or the weak model's quality for every call.

Decided 2026-11-15: every agent step moves to Claude on the paid tier, and each step uses the
model chosen for it.

## Decision

- **Anthropic's API, paid tier.** By default, Anthropic does not train models on API inputs and
  outputs, and deletes them within 30 days. The repository rules do not change: synthetic or
  de-identified data only, in code, tests, fixtures and model calls.
- **Model profiles.** A profile is a checked-in TOML file in the agent module. It maps every
  `Step` (explore, outline, epic_stories, change_explore, change, reply, suggest_tasks) to a binding
  `{provider, model, effort, max_output_tokens, timeout_seconds}`. Each profile has an id and the
  sha256 of its normalized content.
  - When a run is created it pins the profile id, the hash and a copy of the bindings. It uses
    that copy until it finishes, whatever happens to the file.
  - `MODEL_PROFILE` chooses the profile for new runs. The default is `claude-mix-v1`.
  - The API refuses to start when any provider the profile names has no API key. Tests use a
    profile on the `fake` provider. The `replay` provider stays ([ADR 0018](0018-labelled-replay-of-a-recorded-run.md)).
- **`claude-mix-v1`:**

  | Step           | Model               | Effort | Max output tokens | Timeout (s) |
  | -------------- | ------------------- | ------ | ----------------- | ----------- |
  | explore        | `claude-sonnet-5-5` | medium | 12,000            | 180         |
  | outline        | `claude-sonnet-5-5` | high   | 32,000            | 420         |
  | epic_stories   | `claude-haiku-5-5`  | medium | 12,000            | 120         |
  | change_explore | `claude-sonnet-5-5` | medium | 12,000            | 180         |
  | change         | `claude-sonnet-5-5` | high   | 16,000            | 240         |
  | reply          | `claude-haiku-5-5`  | low    | 4,000             | 60          |
  | suggest_tasks  | `claude-haiku-5-5`  | low    | 8,000             | 120         |

- **One model per step, no longer one model per run.** This replaces ADR 0004's "one provider and
  one model per process". A repair always uses the model of the step it repairs. A step's
  conversation stays on one model, and its assistant content, thinking blocks included, is sent
  back exactly as received.
- **No fallback.** The backup provider, the circuit breaker and the free-tier pacing are removed
  (ADR 0006 is superseded). Overload (529), server errors and timeouts return a retryable error,
  and the caller retries as before. A spend limit reached at the provider (`spend_limit`) fails
  the run and is never retried. The server-side refusal fallback stays off. A refusal is
  reported as `blocked`.
- **The adapter.** It uses the official `anthropic` Python SDK 1.x, pinned to an exact version. An
  import-linter contract allows only the Anthropic profile and adapter files to import it. The
  client has SDK retries off and the binding's timeout, and every call is streamed.
  - Typed output is sent as `output_config.format`, with the schema keywords the API does not
    support stripped. Every response is still validated with the full Pydantic model.
  - Every tool is sent with `strict: true`.
  - Each model's profile says whether it supports a forced tool choice. Claude Sonnet 5.5 rejects
    one. On a model that does not support it, the adapter sends `auto` with an instruction to
    answer only by calling a tool. An answer that is text with no tool call is treated as bad
    output, and the step's single repair handles it.
  - Thinking is adaptive: `thinking` is omitted and `output_config.effort` comes from the
    binding. No sampling parameters are sent.
  - Prompts put the stable content first (system prompt, then sources) and one cache breakpoint
    after it. Nothing that changes from call to call comes before the breakpoint.
- **Costs and limits.** The price table holds both models, with the date it was checked. Cache
  reads and writes are tracked and priced. Pre-call budget checks use the binding's model price
  and count expected thinking as output. The run lease (`RUN_LEASE_SECONDS`) must be at least
  twice the profile's longest step timeout, and defaults to 900 s. The default cost limits become
  $1.50 per run and $25 per project.
- **Gemini and Groq are removed completely:** their adapters, profiles and settings,
  `google-genai`, the fallback reason on runs and the free-tier limits. No Gemini profile or
  temporary Gemini path is kept.
- **Evaluations pin a profile** (`--profile`, which replaces `--provider` and `--rpm`). Each report
  records the profile id, its hash and the model for each step.
- **Not measured live yet.** Quality, latency and cost on these models are not yet measured. The
  Flash-Lite results in `evals/README.md` stay as the historical baseline. They are from another
  model and are not compared with Claude results. Alert thresholds are provisional, at twice the
  estimated mean cost per run kind, until a dev-pack report replaces them
  ([ADR 0023](0023-alert-rules-as-code-from-evaluation-results.md)).

## Consequences

- Draft quality is expected to improve, and runs no longer wait for a free tier, but every call
  now costs money. The run and project cost limits are checked before every call.
- Runs and steps record the profile and the step, so cost and quality can be read per step and
  per model.
- A profile change is a new profile id, never an edit to a profile that has reported results.
  Scores stay comparable only within one profile.
- Old runs are not migrated. The database gains the profile columns and loses the provider ones,
  and local databases are reset (`just reset-db`). Nothing is deployed, so no data needs to
  survive.
- The e2e replay was recorded on Flash-Lite. It keeps working while prompts and flow are
  unchanged, and needs re-recording (`just e2e-record`, live) once a step's request changes.
- The first live runs (`just probe-model`, the dev packs, the e2e re-record) happen only after
  asking, and their results go into `evals/README.md` as the new baseline.
- [ADR 0005](0005-durable-agent-runs.md) is unchanged apart from what it pins: the lease rule now
  uses the longest step timeout. [ADR 0022](0022-export-model-call-telemetry-over-otlp.md) and
  ADR 0023 get notes for the step and profile attributes and the new spend-limit alert.

## Notes added 2026-11-15 (the adapter)

The decision is unchanged. What building the adapter settled:

- The SDK is pinned to `anthropic==1.17.0`, the newest 1.x. The 2.x line moves to a newer API
  version and is a separate upgrade.
- Claude refuses a thinking block replayed after the system prompt, the tools or an earlier
  message changed, on accounts created after 2026-08-31 (this one). So the history is
  append-only: every call of a step sends the same system prompt and tools, and thinking blocks
  always go back unchanged. A call that may use only some tools (a reply's last call, an explore
  call with no clarification rounds left) is narrowed without changing them: a forced choice of
  the one tool where the model accepts it (Haiku 5.5, whose forced call then skips thinking), and
  otherwise a system message appended after the last user turn. That message is stored with the
  turn it produced and sent again before it on every later call. Step code still checks which
  tool was called, and a lookup on a reply's last call fails the reply.
- The pre-call worst case prices every prompt token at the cache-write rate, the highest input
  rate, with Haiku's 5x long-prompt rate on top above 100K tokens, so the estimate is never below
  what the call can cost.
- A reply that comes back as text, with no tool call, gets the reply step's single retry when the
  text is not a valid reply. Text that is a valid reply is still accepted, as before.
- The cache breakpoint follows the step's first user message, which holds the sources and the
  request. That message is the same for every call of a step, so repairs and later turns of the
  step read it from the cache.

## Notes added 2026-11-16 (the removal)

The decision is unchanged. What removing Gemini and Groq settled:

- Removed: the Gemini, Groq and OpenAI-compatible adapters, the per-minute pacing, the backup and
  circuit breaker, their settings (`MODEL_PROVIDER`, `MODEL_FALLBACK_PROVIDER`,
  `MODEL_THINKING_LEVEL`, `MODEL_TIMEOUT_SECONDS`, `GEMINI_*`, `GROQ_*`), their prices,
  `google-genai` and `openai`.
- The evaluations and `just probe-model` take `--profile` (default `claude-mix-v1`) in place of
  `--provider`, `--model` and `--rpm`. Runners that drive whole runs route each step to its own
  model; the single-pass and sensitivity runners call the outline step's model. A report records
  the profile id, its hash and each step's binding, and a run's cost is the sum it recorded per
  call. An evaluation stops on a spend limit, as on bad credentials.
- The probe checks each model the profile uses once, through the first step bound to it, and
  writes one report per model.
- The e2e replay is still the Flash-Lite recording. It keeps passing because a replay matches
  calls by their system prompt and order, not by model. Re-recording it on Claude
  (`just e2e-record`) is a live run, done after asking.

## Notes added 2026-11-16 (no choice in the chat)

The decision is unchanged. People do not choose a model or effort: the chat has no picker and
the API takes no model or effort with a message. Every step, replies included, runs on the model
its profile binds, which in `claude-mix-v1` is Sonnet 5.5 or Haiku 5.5. The planned per-message
choice (SSPOC-178, SSPOC-179, SSPOC-180) is dropped.

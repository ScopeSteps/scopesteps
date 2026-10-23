# 0018. Replay a recorded live run, labelled as a replay, for the end-to-end test and demo backup

- Status: Accepted
- Date: 2026-10-20

## Context

The POC needs an end-to-end browser test of the full flow, and a backup for the capstone
demonstration in case live inference is unavailable (POC Implementation Plan, sections 6 and 14).
Both need the agent's steps: questions, a draft, change analysis. A live model in CI would spend
quota, need a key in CI and fail on provider outages; hand-written model answers would test a
model that does not exist. The plan also says a replay may illustrate the UI only if it is labelled,
and must never be presented as a live agent run.

## Decision

- **`MODEL_PROVIDER=replay` answers from a recording** (`MODEL_REPLAY_FILE`) instead of a model.
  It returns the recorded results in order, one per call. A call whose system prompt differs from
  the recorded one is refused (`invalid_request`), so a replay cannot drift into answering steps
  it never recorded, and an exhausted replay refuses further calls.
- **Recordings come from a live run.** With `MODEL_RECORD_FILE` set, the live provider's
  successful results are also written to that file. A recording holds results and a digest of each
  prompt, never the prompts or the sources. Only synthetic packs are recorded.
- **Both are local only.** Settings refuse `replay` and `MODEL_RECORD_FILE` unless `APP_ENV` is
  `local` or `test`, and `replay` cannot have a fallback provider.
- **A replay says so.** Runs made with it are pinned to the provider name `replay`.
  `GET /agent/model` reports `replay: true`, and the web app then shows a banner on every page:
  "Replay, not a live agent."
- **The critical-flow Playwright test runs on the replay by default** (`just e2e`), and re-records
  on the live model with `just e2e-record`, which spends quota and is run only after asking.

## Consequences

- The full flow runs in the browser offline, and repeatably, against real model output.
- A replay proves the application around the model: storage, approval, versions, export, the
  UI. It proves nothing about model quality. That is what the evaluations measure.
- A change to a prompt, a schema, the flow or the demo pack makes the recording stale, and the
  test then fails. Re-record it with `just e2e-record` in the same pull request.
- The demo backup is honest: a recorded replay is visibly labelled, so it cannot pass for a live
  run.

# End-to-end tests

Playwright tests of the POC's critical flow in a real browser, against the real API and web app:
sources, who's who, an agent run with an answered and a skipped question, the cited draft,
approval of v1 by a Product owner, a change request that is rejected while v1 stays, the same
request approved as v2, and the Jira CSV export.

```sh
pnpm --filter @scopesteps/e2e exec playwright install chromium   # once
just e2e                  # the flow on the recorded replay: no model calls
just e2e --headed         # watch it
E2E_VIDEO=on just e2e     # keep a video of every test in test-results/
E2E_VIDEO=on E2E_SLOWMO=500 just e2e   # a video slow enough to follow, e.g. the demo backup
just e2e-record           # re-record on the live model from .env (spends quota: ask first)
```

`playwright.config.ts` starts its own API on port 8011 with a fresh database (`var/e2e.db`,
reset, migrated and seeded by `scripts/start-api.sh`) and the web app on port 5183, so a running
`just api` / `just web` and your local data are left alone. The seeded accounts get a random
password for each run.

## The agent is a replay

By default the API runs with `MODEL_PROVIDER=replay` and answers from
`recordings/campus-room-booking.json`, a recording of one live run of this flow
([ADR 0018](../docs/adr/0018-labelled-replay-of-a-recorded-run.md)). The app shows "Replay, not a
live agent" on every page, and the test checks that it does. A replay proves the application
around the model, never the model's quality; that is measured in [evals/](../evals/README.md).

The test answers the agent's questions the way the evaluation's scripted reviewer does, from the
demo pack's `clarification_answers.yaml`, choosing by what a question is about and skipping the
rest. So the same steps work on the live model and, from its recording, offline.

A change to a prompt, an output schema, the flow or the demo pack makes the recording stale: the
replay then refuses the step that differs and the test fails. Re-record it with
`just e2e-record` in the same pull request. Recording runs the flow on the live model, writes
the new recording and keeps only the model's results, never prompts or sources.

# 0005. Durable agent runs: one leased step per request

- Status: Proposed
- Date: 2026-10-13

## Context

An agent run makes several model calls, may pause for a reviewer's answers, and must survive a
closed tab, a restart, a retry or two requests arriving at once (POC Implementation Plan,
"Run states"). Model calls take 10-30 s and can fail transiently. Holding a database transaction
open across a call would lock the run; running the loop in memory would lose it on restart.
Workflow engines (Temporal and similar) and agent frameworks solve this but add infrastructure
and dependencies the POC does not need.

## Decision

- A run is a row with a status (`created`, `running`, `waiting_for_input`, `ready_for_review`,
  `failed`, `cancelled`), a stage, a `revision` and a lease. Its inputs (source versions, model,
  prompt and schema versions, limits) are pinned at creation.
- `POST /runs/{id}/advance` executes exactly one bounded step: one exploring model call with its
  tools, or the draft with its single repair (the same code the single-pass baseline uses).
  1. A short transaction checks the revision and takes a lease that expires.
  2. The model is called with no transaction open.
  3. A short transaction commits the step only if the revision is unchanged (compare-and-set).
     A result that loses (the run was cancelled, or its expired lease was taken over) is
     discarded, but its usage still counts.
- Writes carry an `Idempotency-Key`; a repeated key returns the run's state without acting again.
- The model only proposes: it can read the run's pinned sources (`lookup_source`) and ask the
  reviewer (`request_clarification`, which pauses the run until every question is answered or
  skipped; the answers become that tool call's result). Code runs `validate_backlog` on every
  draft and decides every transition. No tool approves, publishes or changes permissions.
- Every model call and tool execution is an append-only step row with versions, tokens, latency,
  error kind and estimated cost, and no prompt, source or output text. Turn, tool-call, token and
  cost limits (run and project) are checked before each call and fail closed.
- The finished draft is stored on the run. Turning it into a backlog version is the backlog
  module's job (SSPOC-9), so each module keeps owning its data.

## Consequences

- Runs survive restarts and duplicate requests without a queue or workflow engine. Moving steps
  to a background worker later changes who calls `advance`, not the design.
- The client drives progress by calling `advance` until the run waits or finishes; a closed tab
  pauses the run, and it resumes from its saved state.
- A step that overruns its lease can be taken over, so the lease (`RUN_LEASE_SECONDS`) must
  outlast two model calls; settings enforce at least twice the model timeout.
- A discarded step may have been billed. Its usage is recorded and counts towards the limits.

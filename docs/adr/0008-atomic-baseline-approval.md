# 0008. Atomic baseline approval with append-only decisions

- Status: Accepted
- Date: 2026-10-14

## Context

Approving a draft makes it the project's baseline: the scope later change requests are measured
against and exports are made from. The POC Implementation Plan asks for one transaction that
verifies role and blockers, compares the current baseline and the reviewed revision and hash,
freezes the candidate, records the approval and its audit event and moves the project's
baseline. Two approvers acting at once, a retried request, an edit landing between review and
approval, or a failure part-way must never leave two baselines, a half-approved version or an
approval without its audit event. The local database is SQLite and the hosted one Postgres
(ADR 0003), so the guarantee cannot rest on dialect-specific locking.

Versions live in `backlog`; approvals and baselines belong to `change_control`, which reaches
versions only through `backlog`'s client.

## Decision

- **One transaction.** `POST /backlogs/{id}/approve` runs in `change_control` on the request's
  session: it runs the approval checks again, freezes the version through `backlog.client`,
  inserts the decision, records `backlog.approved` through the audit recorder and stores the
  idempotency receipt, then commits once. Any failure rolls all of it back.
- **Compare-and-set on the version.** Freezing is an `UPDATE` whose `WHERE` names the draft
  state, the reviewed revision and the content hash. Every edit moves the revision in the same
  way, so of an edit and an approval, or of two approvals of one draft, exactly one succeeds.
  An approved version is never updated again; editing it, approving it or rejecting it is
  `409 VERSION_NOT_DRAFT`.
- **The baseline pointer is the newest numbered approval.** `change_control_approvals` is
  append-only. An approval stores `baseline_number` (1 for v1) and the previous baseline; the
  current baseline is the project's approval with the highest number. Each project's baseline
  numbers are unique, so two approvals that read the same baseline compute the same number and
  only one can commit; the other gets `409 DECISION_IN_PROGRESS` and stores nothing.
  `version_id` is unique too, so a version is decided once. Rejections carry no number and never
  move the baseline.
- **Approval binds to what was reviewed.** The request carries `expected_revision`,
  `content_hash` and `expected_baseline_id`; the draft's own base must also be the current
  baseline. Any mismatch is a 409 that changes nothing. The content hash covers the content
  approval freezes, so rejecting a suggestion changes it and approving does not.
- **Checks run on the server, every time.** Structure, citations, reviewed suggestions and
  resolved decisions are checked inside the approval transaction; `POST /backlogs/{id}/review`
  runs the same checks without changing anything, and versions stay `draft` until a decision.
  A decision skipped during the run stays open and blocks approval until a reviewer answers it
  on the draft (`PATCH /backlogs/{id}/decisions/{decision_id}`), so skipping never invents a
  default and never strands a draft.
- **Rejected suggestions are left out of the frozen version.** Freezing removes them from the
  stored items, so the approved snapshot holds exactly what was approved.

## Consequences

- The guarantee holds on SQLite and Postgres with plain `UPDATE ... WHERE` and unique
  constraints; no row locks, advisory locks or serializable isolation are needed.
- There is no mutable pointer row to drift from history. `backlog` still derives a project's
  scope status from its versions' states; both agree because only this transaction approves a
  version and an approved draft must build on the current baseline.
- A concurrent loser reads as `DECISION_IN_PROGRESS` (retryable), a stale reviewer as
  `VERSION_CHANGED` or `BASELINE_CHANGED` (reload and review again).
- `in_review` stays unused by initial drafts; change candidates may use it later.
- A draft made from no baseline cannot be approved once a baseline exists: later work starts
  from a change run based on the current baseline.

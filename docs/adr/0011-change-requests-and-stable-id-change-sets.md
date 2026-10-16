# 0011. Change requests analysed by a change run into a stable-id change set

- Status: Accepted
- Date: 2026-10-15

## Context

Once a baseline is approved, scope moves only through change requests. A reviewer writes what
should change; the agent proposes how; an approver decides. Three risks shape the design: the
model rewriting the whole backlog instead of changing it, a run or a retry touching the approved
baseline, and a request silently undoing an earlier exclusion or decision that people agreed on.
ADR 0010 left `change_request` messages refused with `501` until this analysis existed.

## Decision

- **The request is recorded before analysis.** In one transaction, `agent` checks the requester
  (editor), the text (the message limits of ADR 0010, at most 2,000 characters) and that the
  named baseline id and content hash are still the current baseline's (`409 BASELINE_CHANGED`
  otherwise). It stores the text as an immutable `change_request` source version, so a change can
  cite it; opens the change request in `change_control` (`analyzing`, with its number, author,
  time, base version and hash, and run); creates the change run; posts the thread message; and
  records `change.requested`. Nothing reaches a model before this commits.
- **Two ways in, one use case.** A message sent as `change_request` and `POST /projects/{id}/runs`
  with `mode: "change"` (required `base_version_id`, `base_content_hash` and `request_text`) both
  call it. One change request is analysed at a time per project (`409 AGENT_BUSY`).
- **A change run is a durable run** (ADR 0005). It pins the baseline's own source versions plus
  the request's, and takes the lease, budget and revision checks every step takes. Its explore
  step may ask the reviewer (prompt `change-explore-v1`); its change step (prompt `change-v1`,
  schema `change-set.v1`) returns a change set with at most one repair.
- **The model works on labels, code on stable ids.** The baseline is shown as E1, S1, S1.C1,
  X1 (exclusions) and D1 (decisions); the schema limits every reference to those labels and the
  run's block ids, so another project's ids cannot be named. Code checks every target, citation
  and rule (`find_change_problems`), then maps labels to stable ids (`to_change_proposal`).
- **The candidate is built from the baseline, not from the model's text.** `backlog` copies every
  untouched item with its id, content and provenance and applies only the proposed operations,
  then saves the result as a new version `in_review`. The baseline row is only read: generating,
  retrying, failing or stopping a run never writes it. A deterministic comparison of the two
  (`compare_versions`) is what the API shows and what the request's added, changed and removed
  counts are taken from; the model's own counts are never used.
- **A change, not a rewrite.** A change may modify or remove at most `max(2, ⌈stories/2⌉)`
  baseline stories; more is `wholesale_rewrite`. Removing a story and adding a near-identical one
  is `replaced_not_modified`. Targets that do not exist, criteria on the wrong item, duplicate
  targets and operations citing nothing from the request are refused too.
- **Reversals are a person's decision.** An operation that brings back excluded work or
  contradicts a recorded decision must depend on a scope decision that names what it reverses and
  cites the original evidence. The decision is open on the candidate and blocks it until an
  approver answers it; the model never reverses anything itself.
- **No change needed is an outcome.** When the baseline already covers the request, the run
  completes, the request ends `no_change_needed` with the items that cover it, and no candidate
  is saved.
- **Statuses.** A request is `analyzing`, then `in_review` (candidate saved), `no_change_needed`
  or `failed` (analysis refused or stopped; send it again); deciding the candidate will move it
  to `approved` or `rejected`. Until that lands, a candidate in review cannot be edited or
  approved (`409 VERSION_NOT_DRAFT`).

## Consequences

- An approver reviews exactly the operations proposed, by stable id; unchanged items keep their
  ids and evidence, so v1 to v2 history stays traceable.
- A failed or refused change set leaves nothing but the request (`failed`) and its run; the
  baseline and any earlier candidate are untouched, and the reviewer sends it again.
- The rewrite ceiling may refuse a genuinely broad request. Such a request is a new baseline,
  made by a new initial run.
- Change analysis quality is measured offline on the dev packs' change requests
  (`just evals-change`, [evals/README.md](../../evals/README.md)); it has not been measured live.
- Approving or rejecting a change candidate is a separate decision, made in `change_control` on
  top of these records.

## Notes

- 2026-10-15 (SSPOC-18): deciding a candidate is built. The existing `approve` and `reject`
  routes accept a candidate `in_review` whose request is `in_review`, with the transaction and
  checks of ADR 0008. An approver records `reverse` or `keep` on each scope decision
  (`POST /backlogs/{version}/scope-decisions/{id}`, approver role only, stored on the decision
  with who and when); approval needs every one recorded and `reverse` (`409
SCOPE_DECISION_REQUIRED`, `409 SCOPE_KEPT`), so a `keep` leaves only rejection. The request
  moves to `approved` or `rejected` and `change.approved` or `change.rejected` is recorded in the
  same transaction. No schema change was needed.
- 2026-10-15 (SSPOC-53): `change.approved` and `change.rejected` are also posted to the
  project's conversation (ADR 0010) in the decision's transaction, attributed to the approver and
  naming the change request and the baseline version after the decision (`agent_messages` gains
  `change_request_id` and `baseline_version`). `change_control` reports through a port the
  composition root binds to `agent`, which already builds on `change_control`. The change
  request names the baseline version its approval produced (`approved_version_number`). A
  candidate's open or skipped decisions other than scope decisions, such as a clarification
  skipped during the change run, are answered by an approver
  (`POST /backlogs/{version}/candidate-decisions/{id}`, revision-checked, with who and when);
  closing one is answering it with why. Before this, such a candidate could only be rejected.

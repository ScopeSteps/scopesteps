# scopesteps-change-control

Approved baselines, change requests, scope diffs, approvals and rejections.

The module decides on drafts, approving one as the project's next baseline or rejecting it, and
keeps the project's change requests: what was asked, against which baseline, and what the
analysis proposed. Versions and their content belong to `backlog`, which this module reaches
through its client.

## Public interface

Other modules import only `scopesteps.change_control.client`: `ApprovalId`, `ChangeSetId` and
`ChangeRequestId`, and for the agent's change runs `open_change_request`,
`record_change_analysis` and `record_change_failure` with `OpenChangeRequest`, `ChangeAnalysis`,
`ItemNote`, `ScopeReversal` and `ChangeSummary`. They write in the caller's transaction and
neither check access nor audit: the agent does both
([ADR 0011](../../docs/adr/0011-change-requests-and-stable-id-change-sets.md)).
Everything else is internal and enforced by import-linter. `http/router.py` also has
`resolve_decision_reader`, which the composition root binds to `backlog`'s
`get_decision_reader`, so `backlog` can show who approved a version and when without importing
this module.

## What is where

| Path                             | Contains                                                                                        |
| -------------------------------- | ----------------------------------------------------------------------------------------------- |
| `client.py`                      | Published IDs; opening a change request and recording its analysis                              |
| `domain/errors.py`               | The module's 409 errors                                                                         |
| `domain/change_request.py`       | A change request, its statuses and transitions; the list cursor                                 |
| `application/decisions.py`       | Approve and reject, the decision record and the ports they need                                 |
| `application/change_requests.py` | Open, record analysis or failure, list, read, and the change set                                |
| `infrastructure/orm.py`          | `change_control_approvals`, `change_control_command_receipts`, `change_control_change_requests` |
| `infrastructure/repository.py`   | Decisions, receipts and change requests; the adapter over `backlog`'s client                    |
| `http/`                          | The routes below, and the decision reader `backlog` uses                                        |

Tables are prefixed `change_control_` (ADR 0003).

## API

| Route                                | Does                                                    | Needs    |
| ------------------------------------ | ------------------------------------------------------- | -------- |
| `POST /backlogs/{version}/approve`   | Approves the draft as the project's next baseline       | Approver |
| `POST /backlogs/{version}/reject`    | Rejects the draft; the baseline stays as it is          | Approver |
| `GET /projects/{id}/change-requests` | The project's change requests, newest first, paged      | Any role |
| `GET /change-requests/{id}`          | One change request                                      | Any role |
| `GET /backlogs/{version}/change-set` | What a candidate changes in its baseline, by stable ids | Any role |

`approve` takes `expected_revision`, `content_hash` and `expected_baseline_id` (null for the
first baseline), all as the approver reviewed them (`POST /backlogs/{version}/review` returns
them). `reject` takes `expected_revision` and a `reason` of up to 2,000 characters. Both need an
`Idempotency-Key` and return the decision: `id`, `version_id`, `decision`, `decided_by`,
`revision`, `content_hash`, `decided_at`, `baseline_version` (1 for v1, null for a rejection) and
the project's `current_baseline_id`.

| Rejection                                                     | Status | `code`                   |
| ------------------------------------------------------------- | ------ | ------------------------ |
| Body malformed, or `Idempotency-Key` missing                  | 422    | `VALIDATION_ERROR`       |
| No such version, or not a member of its project               | 404    | `NOT_FOUND`              |
| Member without the Approver role                              | 403    | `PERMISSION_DENIED`      |
| The version is already approved or rejected                   | 409    | `VERSION_NOT_DRAFT`      |
| The revision or content hash is not the current one           | 409    | `VERSION_CHANGED`        |
| The baseline is not the expected one, or not the draft's base | 409    | `BASELINE_CHANGED`       |
| A check failed (approve only)                                 | 409    | `APPROVAL_BLOCKED`       |
| A concurrent decision committed first                         | 409    | `DECISION_IN_PROGRESS`   |
| Key reused for a different request                            | 409    | `IDEMPOTENCY_KEY_REUSED` |

`APPROVAL_BLOCKED` carries every check in `details.checks`, in the shape `review` returns.
`BASELINE_CHANGED` carries `details.current_baseline_id` and `details.base_version_id`.
`DECISION_IN_PROGRESS` is retryable: a retry returns the decision (same key) or the precise
conflict. The others mean what was reviewed is stale: reload and review again.

## Rules

- **One transaction per decision** ([ADR 0008](../../docs/adr/0008-atomic-baseline-approval.md)):
  the checks, the frozen version, the decision row, the audit event and the receipt commit
  together or not at all.
- **The checks run again on approval**, whatever the reviewer saw: structure, citations,
  reviewed suggestions and resolved decisions (see `backlog`'s README).
- **Approved versions never change.** Freezing compares the draft state, revision and hash in
  the `UPDATE` itself and leaves rejected suggestions out of the stored version.
- **The baseline is the newest numbered approval.** Decisions are only ever inserted; an
  approval stores its baseline number and the baseline it replaced. Unique
  `(project_id, baseline_number)` and unique `version_id` stop two decisions from advancing the
  same baseline or deciding one version twice.
- **A draft must build on the current baseline.** Its `base_version_id` must be the baseline when
  it is approved; a draft made before another was approved cannot replace it.
- **Decisions are audited** as `backlog.approved` and `backlog.rejected`, attributed to the
  approver, with counts only. A rejection's reason is stored on the decision, never in the log.
- **Commands are idempotent per actor and key.** A repeated command returns the recorded
  decision without checking or acting again.

Tested with in-memory fakes in `tests/test_decisions.py`, and through the API and the database
(atomicity, concurrency, permissions, restart) in `apps/api/tests/test_backlog_approval.py`.

## Change requests

A change request is sent through the agent (a `change_request` message, or a run created in
`change` mode; see `agent`'s README), which opens it here in the transaction that creates its
run, before any analysis ([ADR 0011](../../docs/adr/0011-change-requests-and-stable-id-change-sets.md)).
Each request stores `id`, `number` (CR-1, CR-2, ... never reused), `text`, `requested_by` (id and
name as it was), `requested_at`, `base_version_id` and `base_content_hash`, the
`source_version_id` its text was stored as, its `run_id` and its `status`:

| Status             | Means                                                                  |
| ------------------ | ---------------------------------------------------------------------- |
| `analyzing`        | The change run is working on it                                        |
| `in_review`        | A candidate was saved beside the baseline (`candidate_version_id`)     |
| `no_change_needed` | The baseline already covers it; no candidate                           |
| `failed`           | The analysis was refused or stopped (`failure` holds the error code)   |
| `approved`         | Its candidate was approved (set by the change decision, not yet built) |
| `rejected`         | Its candidate was rejected (set by the change decision, not yet built) |

An analysis is recorded exactly once, compare-and-set on the request's revision. The `summary`
(`added`, `changed`, `removed`) is counted from a stable-id comparison of the saved candidate
with the baseline (`backlog`'s `compare_versions`), never taken from the model.

`GET /projects/{id}/change-requests?limit=&cursor=` lists them newest first (time, then id);
`limit` is 1 to 100 (default 20) and `next_cursor` reads the next, older page until it is null.
Each entry also carries `base_version_number`, `candidate_version_id`, `summary`, `analysis` (the
agent's words), `failure` and `analyzed_at`. A cursor this list did not return is
`422 INVALID_CURSOR`; a project or request the actor cannot see is `404 NOT_FOUND`.

`GET /backlogs/{version}/change-set` returns, for a candidate a request proposed, its id, the
request, both versions and content hashes, the `operations` (shaped like `compare`'s, each with
the agent's `rationale`), `removed_exclusions` with their original evidence, `scope_decisions`
(each reversal of an exclusion or earlier decision, as an open decision on the candidate),
`open_decision_ids` and `impacts`. Any other version is `404 NOT_FOUND`.

Tested with in-memory fakes in `tests/test_change_requests.py` and end to end in
`apps/api/tests/test_change_requests.py`.

## Not here yet

- Approving or rejecting a change candidate, which moves its request to `approved` or
  `rejected`. Until then a candidate in review cannot be edited or decided
  (`409 VERSION_NOT_DRAFT`).

# scopesteps-change-control

Approved baselines, change requests, scope diffs, approvals and rejections.

Today the module decides on drafts: approving one as the project's next baseline, or rejecting
it. Versions and their content belong to `backlog`, which this module reaches through its
client; change requests and diffs come later.

## Public interface

Other modules import only `scopesteps.change_control.client`: `ApprovalId` and `ChangeSetId`.
Everything else is internal and enforced by import-linter. `http/router.py` also has
`resolve_decision_reader`, which the composition root binds to `backlog`'s
`get_decision_reader`, so `backlog` can show who approved a version and when without importing
this module.

## What is where

| Path                           | Contains                                                        |
| ------------------------------ | --------------------------------------------------------------- |
| `client.py`                    | Published IDs                                                   |
| `domain/errors.py`             | The module's 409 errors                                         |
| `application/decisions.py`     | Approve and reject, the decision record and the ports they need |
| `infrastructure/orm.py`        | `change_control_approvals`, `change_control_command_receipts`   |
| `infrastructure/repository.py` | Decisions and receipts; the adapter over `backlog`'s client     |
| `http/`                        | The routes below, and the decision reader `backlog` uses        |

Tables are prefixed `change_control_` (ADR 0003).

## API

| Route                              | Does                                              | Needs    |
| ---------------------------------- | ------------------------------------------------- | -------- |
| `POST /backlogs/{version}/approve` | Approves the draft as the project's next baseline | Approver |
| `POST /backlogs/{version}/reject`  | Rejects the draft; the baseline stays as it is    | Approver |

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

## Not here yet

- Change requests and their change sets. The list of a project's versions with their decisions,
  and a stable-id comparison of any two, are in `backlog`.

# scopesteps-backlog

Requirements, epics, stories, acceptance criteria, dependencies and backlog versions.

A backlog version holds its epics and stories, the decisions raised about them (open, skipped or
answered by a reviewer) and the work the sources exclude or only suggest. Agent runs propose
candidates; this module validates them and saves them as draft versions, lets editors change a
draft, and runs the checks a draft must pass before approval. Approving or rejecting is
`change_control`'s action; it freezes the version through this module's client
([ADR 0008](../../docs/adr/0008-atomic-baseline-approval.md)).

## Public interface

Other modules import only `scopesteps.backlog.client`: the ids, the API DTOs, and
`CandidateProposal` with `candidate_problems`, `save_candidate` and `find_candidate`;
`load_scope_statuses` with `ScopeStatus`; and, for decisions, `load_version_summary`,
`approval_checks`, `freeze_approved` and `mark_rejected` with `VersionSummary`, `CheckResult`,
`VersionChangedError` and `VersionNotDraftError`. Everything else is internal and enforced by
import-linter.

## What is where

| Path                           | Contains                                                                 |
| ------------------------------ | ------------------------------------------------------------------------ |
| `client.py`                    | Published IDs, DTOs and the candidate functions agent runs call          |
| `domain/version.py`            | Version, items, criteria, decisions, scope notes; blockers; content hash |
| `domain/candidate.py`          | A run's proposal, its structural checks and how it becomes a draft       |
| `domain/editing.py`            | A person's edit to one item, and the version's 409 errors                |
| `domain/review.py`             | The four approval checks                                                 |
| `domain/status.py`             | A project's scope status, derived from its versions' states              |
| `application/candidates.py`    | Validate and save a candidate once per run; read a version               |
| `application/editing.py`       | Edit an item of a draft, idempotently; review a version                  |
| `infrastructure/orm.py`        | `backlog_versions`, `backlog_item_revisions`, `backlog_command_receipts` |
| `infrastructure/repository.py` | Versions as rows with schema-versioned JSON; revision-checked writes     |
| `http/`                        | The routes below; export is 501                                          |

Tables are prefixed `backlog_` (ADR 0003).

## Rules the domain enforces

- **Ceilings, not quotas.** At most 2 epics and 8 stories; fewer is always valid.
- **A candidate is validated before it is saved.** Duplicate item refs, a story without an epic,
  a parent that is not an epic, counts over the ceilings, decisions that name unknown items, and
  evidence that does not resolve to a paragraph of a source version the run pinned in this
  project (checked by `evidence`) all reject the whole candidate with `CANDIDATE_REJECTED`.
- **A claim is only as strong as its support.** A criterion's origin is derived, not taken on
  trust: `human` when a reviewer's answer confirms it, `source` when a stored passage backs it,
  otherwise `proposed`. A detail the agent added stays `proposed` whatever it cites.
- **Blockers are derived on every read**, so they cannot outlive their cause: an unresolved
  decision blocks the items it affects (or the version, if it affects none), and an agent
  suggestion (a `proposed` criterion, with no source) blocks its item while its `suggestion` is
  `pending`, until an editor accepts, rejects, rewrites or removes it.
- **Only an answer resolves a decision.** A skipped decision stays unresolved and keeps who
  skipped it and when.
- **A project's scope status is derived, never stored.** The current baseline is the newest
  approved version and its number is the count of approved versions. A draft or a candidate in
  review counts as in flight only if it is newer than that baseline; rejected versions never
  count. `load_scope_statuses` answers for any number of projects with one query.
- **One candidate per run.** `backlog_versions.run_id` is unique, so a retried or duplicated
  step cannot save a second draft.
- **Saving a draft is the agent's action.** A newly saved candidate records a
  `backlog.draft_saved` audit event, attributed to the agent, in the same transaction.

- **Only drafts change, and only at the revision the editor saw.** An edit names
  `expected_revision`; the revision is compared in the `UPDATE` itself, so a stale edit is
  `409 VERSION_CHANGED` and saves nothing. Every saved edit moves the revision and recomputes the
  content hash. An approved or rejected version is never changed again: an edit is
  `409 VERSION_NOT_DRAFT`. Later work starts a new draft.
- **Ids are stable.** An edited item or criterion keeps its id, origin and evidence. A criterion
  a person adds gets a new id and the `person` origin. Removing a criterion drops it from the
  draft; rejecting a suggestion keeps it visible (so it can be reopened) but leaves it out of the
  approved version.
- **Human provenance is stored.** An item records `human_edited` once a person changes its
  title, description or criteria, and `edited_by`/`edited_at` for the latest change; a criterion
  whose text a person wrote records `edited_by`. Each saved edit records a
  `backlog.item_edited` audit event with counts only, in the edit's transaction.
- **The content hash covers what approval would freeze**, so rejecting a suggestion changes it
  and approving does not ([ADR 0008](../../docs/adr/0008-atomic-baseline-approval.md)).
- **Edits are idempotent per actor and key.** A repeated edit returns the version as it is now;
  the same key with a different edit is `409 IDEMPOTENCY_KEY_REUSED`. An edit that changes
  nothing saves nothing and keeps the revision.
- **Approval checks** (`structure_valid`, `citations_resolve`, `suggestions_reviewed`,
  `decisions_resolved`) run on the content approval would freeze: ids, hierarchy and ceilings;
  every cited passage resolves to a stored paragraph of a source version the draft was made
  from; no suggestion is pending; no decision is open or skipped. Problems name ids and counts
  only.

## API

| Route                                      | Does                                                       | Needs              |
| ------------------------------------------ | ---------------------------------------------------------- | ------------------ |
| `GET /projects/{id}/backlogs/{version}`    | A version with its items, evidence, decisions and blockers | Any role           |
| `PATCH /backlogs/{version}/items/{id}`     | Edits one item of a draft; returns the whole version       | Editor             |
| `PATCH /backlogs/{version}/decisions/{id}` | Answers an open or skipped decision on a draft             | Editor or approver |
| `POST /backlogs/{version}/review`          | Runs every approval check; changes nothing                 | Any role           |

A version of a project the actor has no role in is `404 NOT_FOUND`, exactly like one that does
not exist. Approving and rejecting are in `change_control`'s README.

`PATCH` takes `expected_revision` and any of `title`, `description` and `criteria`. `criteria` is
the item's whole new list in order, each `{"id", "text", "suggestion"}`: `id` null adds a
criterion; `suggestion` (`pending`, `accepted`, `rejected`) is only for agent suggestions, and
null leaves it as it is; rewriting a suggestion's text accepts it. Both commands need an
`Idempotency-Key`; `review` has no side effects, so repeating it is always safe.

A decision skipped during the run stays unresolved and blocks approval (the POC plan: "skipped
material decision remains unresolved/blocking"). Answering it on the draft is how it gets
settled: `PATCH /backlogs/{version}/decisions/{id}` takes `expected_revision` and `answer` (1 to
2000 characters after trimming), records who decided and when, moves the draft to its next
revision and records `scope.decided`. An answered decision keeps its answer
(`409 DECISION_ALREADY_ANSWERED`); an empty, long or unprintable one is
`422 DECISION_ANSWER_INVALID`. It needs an `Idempotency-Key` like the other commands.

`review` takes `expected_revision` and returns the `revision`, `content_hash`, `epic_count`,
`story_count`, the project's `baseline_version_id` (send it to `approve` as
`expected_baseline_id`), `ready` and every check as `{"code", "title", "passed", "problems",
"problem_count"}`.

| Rejection                                               | Status | `code`                   |
| ------------------------------------------------------- | ------ | ------------------------ |
| Body malformed, or `Idempotency-Key` missing            | 422    | `VALIDATION_ERROR`       |
| Unknown criterion, empty text, misuse of `suggestion`   | 422    | `ITEM_EDIT_INVALID`      |
| No such version or item, or not a member of its project | 404    | `NOT_FOUND`              |
| Member without the Editor role (edits)                  | 403    | `PERMISSION_DENIED`      |
| `expected_revision` is not the current revision         | 409    | `VERSION_CHANGED`        |
| The version is approved or rejected                     | 409    | `VERSION_NOT_DRAFT`      |
| Key reused for a different request                      | 409    | `IDEMPOTENCY_KEY_REUSED` |

`VERSION_CHANGED` carries `details.current_revision` and `details.content_hash`;
`ITEM_EDIT_INVALID` carries `details.problems`.

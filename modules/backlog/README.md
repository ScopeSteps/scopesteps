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
`VersionChangedError` and `VersionNotDraftError`. For the agent's conversation it publishes
`current_backlog` (the version in flight or the baseline, as a `BacklogOutline` without evidence)
and `change_run_answer`, which writes a changed clarification answer into a run's draft and moves
it to its next revision (ADR 0010). It also publishes `get_decision_reader`, a
FastAPI dependency for how a version was decided (`VersionDecision`, read through
`DecisionReader`): `change_control` records approvals and builds on this module, so the
composition root binds the dependency to `change_control`'s reader. Everything else is internal
and enforced by import-linter.

## What is where

| Path                           | Contains                                                                 |
| ------------------------------ | ------------------------------------------------------------------------ |
| `client.py`                    | Published IDs, DTOs and the candidate functions agent runs call          |
| `domain/version.py`            | Version, items, criteria, decisions, scope notes; blockers; content hash |
| `domain/candidate.py`          | A run's proposal, its structural checks and how it becomes a draft       |
| `domain/editing.py`            | A person's edit to one item, and the version's 409 errors                |
| `domain/review.py`             | The four approval checks                                                 |
| `domain/history.py`            | A version's listing, the list cursor, and the stable-id comparison       |
| `domain/status.py`             | A project's scope status, derived from its versions' states              |
| `domain/version_decision.py`   | How a version was decided, and the port that reads it                    |
| `domain/export.py`             | The approved snapshot, its Markdown and its download name                |
| `application/candidates.py`    | Validate and save a candidate once per run; read a version               |
| `application/editing.py`       | Edit an item of a draft, idempotently; review a version                  |
| `application/exporting.py`     | Export an approved version for any member                                |
| `application/history.py`       | List a project's versions a page at a time; compare two versions         |
| `infrastructure/orm.py`        | `backlog_versions`, `backlog_item_revisions`, `backlog_command_receipts` |
| `infrastructure/repository.py` | Versions as rows with schema-versioned JSON; revision-checked writes     |
| `http/`                        | The routes below                                                         |

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
| `GET /projects/{id}/backlogs`              | The project's versions, newest first, paged by cursor      | Any role           |
| `GET /projects/{id}/backlogs/compare`      | What changes between two versions, by stable ids           | Any role           |
| `GET /projects/{id}/backlogs/{version}`    | A version with its items, evidence, decisions and blockers | Any role           |
| `PATCH /backlogs/{version}/items/{id}`     | Edits one item of a draft; returns the whole version       | Editor             |
| `PATCH /backlogs/{version}/decisions/{id}` | Answers an open or skipped decision on a draft             | Editor or approver |
| `POST /backlogs/{version}/review`          | Runs every approval check; changes nothing                 | Any role           |
| `GET /backlogs/{version}/export`           | Downloads an approved version as JSON or Markdown          | Any role           |

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
| A list `cursor` this list did not return                | 422    | `INVALID_CURSOR`         |
| Export of a draft, a candidate in review or a rejection | 409    | `VERSION_NOT_APPROVED`   |
| Export `format` other than `json` or `markdown`         | 422    | `VALIDATION_ERROR`       |

`VERSION_CHANGED` carries `details.current_revision` and `details.content_hash`;
`ITEM_EDIT_INVALID` carries `details.problems`; `VERSION_NOT_APPROVED` carries `details.state`.

## Export

`GET /backlogs/{version}/export?format=json|markdown` (JSON when `format` is left out) returns
the version exactly as it was frozen on approval, never the project's latest baseline or a draft:
exporting v1 after v2 exists returns v1. Any member may export, viewers included; a non-member
gets `404 NOT_FOUND` before the version's state is looked at, so nothing about it leaks. It is a
read: nothing is stored and no audit event is recorded.

- **JSON** (`application/json`, `BacklogExport`): `schema_version`
  (`scopesteps.backlog-export.v1`), `exported_at`, `project` (`id`, `name`), `version` (`id`,
  `number` as in v1, `state`, `revision`, `content_hash`, `base_version_id`, `run_id`,
  `source_version_ids`, `created_at`, `approved_by`, `approved_at`), `items` with their
  stable ids, hierarchy (`parent_id`), criteria (`id`, `text`, `origin`, `evidence`,
  `confirmed_by`), assumptions, open questions and `human_edited`; `decisions`, `out_of_scope`
  and `withheld_evidence_count`.
- **Markdown** (`text/markdown; charset=utf-8`): the same content as readable text, each epic
  followed by its stories, with every id, origin label and evidence locator. Text from sources,
  the agent or people is escaped and kept on one line (descriptions keep their paragraphs), so it
  can never become a heading, list, link, image, table or HTML.
- **Download name** in `Content-Disposition`: `<project-slug>-backlog-v<number>.<json|md>`, ASCII
  letters, digits and hyphens only. The API exposes the header to cross-origin callers.

**Evidence policy.** Every member may read every source of the project, so the export carries
each citation's ids, quote and relationship. Citations are checked against the stored passages
again on every export; one that no longer resolves to a passage of the version's project is left
out and counted in `withheld_evidence_count`. Items have no dependencies yet other than the epic
and story hierarchy, which `parent_id` carries.

## Version history and comparison

Both are reads for any member of the project; a non-member gets `404 NOT_FOUND`.

`GET /projects/{id}/backlogs?limit=&cursor=` lists every version of the project, drafts and
rejections included, newest first (creation time, then id). `limit` is 1 to 100 (default 20);
send `next_cursor` back as `cursor` for the next, older page, until it is null. Each entry has
`id`, `number` (the baseline number of an approved version, otherwise null), `state`,
`revision`, `content_hash`, `base_version_id`, `run_id` (the agent run that proposed it),
`created_by`, `created_at` and `decision` (`decision`, `decided_by`, `decided_at`: the approver
and approval time, or who rejected it and when; null while undecided). A page costs two queries
whatever its size: the version rows, then their decisions from `change_control`.

`GET /projects/{id}/backlogs/compare?base=&candidate=` compares any two versions of the project,
in either order. Items and criteria are matched by their stable ids, never by text, and each
version is compared as approval freezes it, so a rejected suggestion counts as absent. The
response names both versions and their content hashes and lists `operations` in the shape of a
change set's: `kind` (`add_item`, `modify_item` or `remove_item`), `item_id`, `before` and
`after` (whole items), `changed_fields` (the item's own fields that differ) and `criteria` (each
`added`, `removed` or `modified`, with its `criterion_id`, `before` and `after`). Provenance alone
(who edited, a suggestion's review state) is not a change. A version of another project is
`404 NOT_FOUND`, exactly like a missing one.

# scopesteps-backlog

Requirements, epics, stories, acceptance criteria, dependencies and backlog versions.

A backlog version holds its epics and stories, the decisions raised about them (open, skipped or
answered by a reviewer) and the work the sources exclude or only suggest. Agent runs propose
candidates; this module validates them and saves them as draft versions. Nothing here approves a
version: that is `change_control` (SSPOC-11).

## Public interface

Other modules import only `scopesteps.backlog.client`: the ids, the API DTOs, and
`CandidateProposal` with `candidate_problems`, `save_candidate` and `find_candidate`. Everything
else is internal and enforced by import-linter.

## What is where

| Path                           | Contains                                                                 |
| ------------------------------ | ------------------------------------------------------------------------ |
| `client.py`                    | Published IDs, DTOs and the candidate functions agent runs call          |
| `domain/version.py`            | Version, items, criteria, decisions, scope notes; blockers; content hash |
| `domain/candidate.py`          | A run's proposal, its structural checks and how it becomes a draft       |
| `application/candidates.py`    | Validate and save a candidate once per run; read a version               |
| `infrastructure/orm.py`        | `backlog_versions`, `backlog_item_revisions`                             |
| `infrastructure/repository.py` | Versions as rows with schema-versioned JSON payloads                     |
| `http/`                        | `GET /projects/{id}/backlogs/{version}`; edit, review and export are 501 |

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
  decision blocks the items it affects (or the version, if it affects none), and a `proposed`
  criterion blocks its item until a reviewer accepts, edits or removes it.
- **Only an answer resolves a decision.** A skipped decision stays unresolved and keeps who
  skipped it and when.
- **One candidate per run.** `backlog_versions.run_id` is unique, so a retried or duplicated
  step cannot save a second draft.

## API

| Route                                   | Does                                                       |
| --------------------------------------- | ---------------------------------------------------------- |
| `GET /projects/{id}/backlogs/{version}` | A version with its items, evidence, decisions and blockers |

Reading needs any role on the project. A version of another project is `404 NOT_FOUND`, exactly
like one that does not exist.

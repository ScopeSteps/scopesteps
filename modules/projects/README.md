# scopesteps-projects

Projects and the people on them: the people their sources name, with corrections and confirmed
decision rights, and the participants editors confirm as a transcript's speakers.

An agent run reads people out of the sources (name, role, a one-sentence summary of what they
said, any decision right a source states, and citations). This module stores that reading and,
beside it, what people on the project change: a corrected name or role, a confirmed decision
right where the sources state none, and who each transcript speaker is with their meeting role
(ADR 0012). The agent never writes any of these.

It also holds projects themselves: listing the ones a user belongs to, creating one, renaming
it, and reporting the limits that apply to work in it. Memberships and roles belong to
`identity`, a project's scope status to `backlog` and the activity log to `audit`; this module
reaches them through their clients.

## Public interface

Other modules import only `scopesteps.projects.client`. Everything else is internal and
enforced by import-linter.

| Name                                                  | Is                                                                |
| ----------------------------------------------------- | ----------------------------------------------------------------- |
| `ProjectId`, `PersonId`                               | Ids                                                               |
| `ProjectRef`, `get_project_reader`                    | A project's current name, for labelling versions and exports      |
| `ExtractedPerson`, `PersonEvidence`, `StatedRights`   | What a run hands over about one person                            |
| `extraction_problems`, `name_key`, the `MAX_*` limits | The rules a handed-over person must meet, so the agent checks too |
| `PeopleRecorder`, `get_people_recorder`               | Stores a run's people in the caller's transaction                 |

`client.py` stays free of SQLAlchemy because domain code in other modules imports `ProjectId`
from it. `get_project_reader` and `get_people_recorder` are therefore FastAPI dependencies the
composition root binds (`apps/api/.../main.py`), not functions that take a session.

## What is where

| Path                           | Contains                                                             |
| ------------------------------ | -------------------------------------------------------------------- |
| `client.py`                    | Published ids, the extracted-person values and the two dependencies  |
| `domain/project.py`            | `Project`, the name rule (`normalize_name`), the project errors      |
| `domain/limits.py`             | `ProjectLimits`, filled in by the composition root from settings     |
| `domain/extraction.py`         | What a run hands over, its size limits and `name_key`                |
| `domain/person.py`             | A person: extraction, entered name, meeting role, correction, rights |
| `domain/speakers.py`           | Speaker answers per source and how each label resolves               |
| `application/projects.py`      | List, read, create and rename; the ports they need                   |
| `application/people.py`        | Store a run's people, list, correct, confirm rights                  |
| `application/speakers.py`      | List every transcript's speakers; save an editor's whole answer      |
| `application/receipts.py`      | The idempotency receipt every command here takes                     |
| `infrastructure/orm.py`        | Projects, people, receipts, speaker mappings and assignments         |
| `infrastructure/repository.py` | Projects and people with revision-checked writes; command receipts   |
| `http/`                        | The routes below, and the people recorder the composition root binds |

Tables are prefixed `projects_` (ADR 0003).

## Projects API

| Route                  | Does                                                       | Needs              |
| ---------------------- | ---------------------------------------------------------- | ------------------ |
| `GET /projects`        | The actor's projects by name, with roles and status        | Signed in          |
| `POST /projects`       | Creates a project; the actor becomes its editor + approver | Signed in          |
| `GET /projects/{id}`   | One project with its roles, status and `limits`            | Any role on it     |
| `PATCH /projects/{id}` | Renames it                                                 | Editor or Approver |

`POST` takes `{"name"}` and returns 201. `PATCH` takes `{"name", "expected_revision"}`. Both need
an `Idempotency-Key` header, and both return the same body as `GET /projects/{id}`. The list
returns `{"projects": [...]}` with the same fields except `limits`.

| Field      | Meaning                                                                                            |
| ---------- | -------------------------------------------------------------------------------------------------- |
| `roles`    | Every role the actor holds in the project, e.g. `["editor", "approver"]`                           |
| `revision` | Starts at 1 and goes up with every rename; send it back as `expected_revision`                     |
| `status`   | `state`, `baseline_version`, `baseline_version_id`, `open_version_id` (see below)                  |
| `limits`   | `project_name_max_chars`, and `source`, `run`, `backlog` and `conversation` ceilings (detail only) |

| Rejection                                       | Status | `code`                        |
| ----------------------------------------------- | ------ | ----------------------------- |
| Name blank, over 80 characters or not printable | 422    | `PROJECT_NAME_INVALID`        |
| Body malformed, or `Idempotency-Key` missing    | 422    | `VALIDATION_ERROR`            |
| Not a member of the project, or no such project | 404    | `NOT_FOUND`                   |
| Member without the Editor or Approver role      | 403    | `PERMISSION_DENIED`           |
| `expected_revision` is not the current revision | 409    | `PROJECT_CHANGED`             |
| Key reused for a different request              | 409    | `IDEMPOTENCY_KEY_REUSED`      |
| A concurrent request with the same key won      | 409    | `PROJECT_COMMAND_IN_PROGRESS` |

`PROJECT_NAME_INVALID` carries `details.field` (`name`) and `details.max_chars`;
`PROJECT_CHANGED` carries `details.current_revision`.

### Project rules

- **Names.** A name is stored in Unicode NFC, trimmed, with every run of whitespace (tabs and
  line breaks included) collapsed to one space. It must then be 1 to 80 code points and printable: control and invisible characters (zero-width spaces, direction overrides) are rejected. The limit is reported as
  `limits.project_name_max_chars`.
- **Names are not unique.** A project is identified by its id; nothing in the product looks one
  up by name, and two teams may reasonably use the same name. The list orders by name, then id.
- **Any signed-in user may create a project**, and becomes its Editor and Approver in the same
  transaction as the project row. Roles combine and none implies another (see `identity`), so
  the creator needs both: Editor to add sources and rename, Approver to approve scope. This
  matches the seeded local reviewer.
- **Renames are revision-checked.** The stored revision is compared in the `UPDATE` itself, so
  of two writers holding the same revision one succeeds and the other gets `PROJECT_CHANGED`.
  Renaming to the name the project already has succeeds without moving the revision.
- **A rename is recorded in the activity log** as `project.renamed`, through `audit`'s recorder
  in the rename's own transaction, with the old and the new name in the summary. A rename that
  changes nothing, a repeated command and a rejected one record nothing. Creating a project
  records nothing: the activity list has no such event.
- **Commands are idempotent per actor and key.** A repeated create returns the project it
  created; a repeated rename returns the project as it is now, without checking the revision
  again. A request that was rejected leaves no receipt, so it can be corrected under the same
  key. Project and people commands share one receipt table, `projects_command_receipts`; the
  fingerprint covers the operation and its values, so one key never serves two commands.
- **Status comes from `backlog`** (`load_scope_statuses`), derived from stored versions on every
  read; the whole list costs one query there. `state` is `candidate_in_review` or
  `draft_in_progress` while work newer than the current baseline is in flight, otherwise
  `baseline`, or `no_baseline` if nothing was ever approved. `baseline_version` (1 for the first
  approved version) and `baseline_version_id` are set whenever a baseline exists, and
  `open_version_id` names the candidate or draft the state refers to.
- **Limits are reported, not enforced, here.** `sources`, `agent` and `backlog` enforce them;
  the composition root copies the same settings and constants into `ProjectLimits`.
- The list is not paginated: a user's projects are few in the POC.

## People

### Rules the domain enforces

- **The extraction is never edited.** A correction and a confirmed right live in their own
  columns with who made them and when; every read returns the agent's reading (`extracted`), the
  correction and the confirmed right separately, plus the effective `name` and `role`.
- **A right is stated only with a citation.** `stated_rights` is `decides` or `advises` only when
  `rights_evidence` points at the passage that states it; otherwise it is `not_stated`.
- **Confirming is for rights the sources do not state.** Confirming `decides`, `advises` or
  `unknown` on a person whose right a source states is refused (`RIGHTS_STATED_IN_SOURCE`).
  `unknown` records that someone looked and could not say; no confirmation means nobody has.
- **Only what the People page shows is kept.** A person is a named individual, so a row holds a
  name, a role, one model-written sentence (not source text) and at most two citations each for
  the person and the right, all bounded in length. A quote longer than the limit is stored as a
  citation of the whole paragraph.

### When a later run extracts again

Deterministic and by name only (`record_extracted_people`). Names are compared after Unicode
normalisation, case-folding and collapsing spaces.

1. A person whose extracted name matches gets the new reading.
2. Otherwise a person whose corrected name matches gets it (the agent read the name wrongly once
   and someone fixed it).
3. Otherwise the person is added.

The correction and the confirmed right always survive. The revision moves only when the reading
changed, so an unchanged re-read does not invalidate an open edit. Nobody is removed: a later run
may read fewer sources. There is no fuzzy matching, so "Dana" and "Dana Ruiz" are two people
until someone corrects one; merging people is not built.

### People API

| Route                                           | Does                                      | Needs         |
| ----------------------------------------------- | ----------------------------------------- | ------------- |
| `GET /projects/{id}/people`                     | Everyone the sources name, oldest first   | Any role      |
| `PUT /projects/{id}/people/{person}/correction` | Set the corrected name and role           | `editor` role |
| `PUT /projects/{id}/people/{person}/rights`     | Confirm `decides`, `advises` or `unknown` | `editor` role |

Correcting and confirming are edits, so they need the Editor role like every other edit; roles
do not imply one another, so an approver who is not an editor can only read.

Both writes take an `Idempotency-Key` and `expected_revision`. A correction is the whole
correction: `null`, or the agent's own value, leaves that field uncorrected, so sending the
original back removes it. Errors use the shared envelope:

| Status | Code                          | When                                                                                         |
| ------ | ----------------------------- | -------------------------------------------------------------------------------------------- |
| 403    | `PERMISSION_DENIED`           | A member without the `editor` role tries to change a person                                  |
| 404    | `NOT_FOUND`                   | Not a member of the project, or the person is not in it                                      |
| 409    | `PERSON_CHANGED`              | `expected_revision` is stale; `details.current_revision`                                     |
| 409    | `RIGHTS_STATED_IN_SOURCE`     | Confirming a right a source already states                                                   |
| 409    | `IDEMPOTENCY_KEY_REUSED`      | The key was used for a different request                                                     |
| 409    | `PROJECT_COMMAND_IN_PROGRESS` | A concurrent request with the same key won                                                   |
| 422    | `VALIDATION_ERROR`            | Body malformed, a name or role over 80 characters, an unknown right, or no `Idempotency-Key` |
| 422    | `INVALID_INPUT`               | A name that is blank once trimmed                                                            |

A retry with the same key and body returns the person as they are now without acting again. A
correction that leaves the shown name and role as they were, or confirming the right already
confirmed, succeeds without moving the revision.

Each change is recorded in the activity log through `audit`'s recorder, in the change's own
transaction: `person.corrected` ("Corrected a person's name and role") and
`person.rights_confirmed` ("Confirmed that a person decides scope"). The summary names no
person, because the name comes from the sources or the model; the event's `person` subject
carries the id. A no-op, a repeated command and a rejected one record nothing.

`corrected_by` and `confirmed_by` are user ids; `GET /projects/{id}/members` in `identity` names
them.

The list is not paginated: a run names at most 10 people and a project's sources name few.

Use cases are tested with in-memory fakes in `tests/`, and end to end, from a scripted run to the
routes, in `apps/api/tests/test_people.py`.

## Who's who in transcripts

Speaker labels are found by `sources` (`load_current_speakers`); this module never reads source
text. It keeps, per source and label key, an editor's answer: a participant, or not a person
(ADR 0012).

### Rules

- **Participants.** A person has an `origin`: `extracted` when a run first named them, and
  `confirmed_speaker` when an editor created them for a speaker. A participant's `entered_name`
  and `meeting_role` are values of their own, never a correction, and a run never writes them.
  `extracted` is null until a run names the person. The migration back-fills existing people
  as `extracted`; their corrections and confirmed rights are unchanged.
- **Runs.** `record_extracted_people` also matches a participant by their entered name, so a
  run's reading fills in a confirmed participant instead of adding a second person.
- **Kept per source, not per version.** A corrected version keeps its answers. A label the new
  version no longer has drops out of the list and is removed on the next save.
- **Whole answer, revision-checked.** A save replaces the transcript's answers; a label left out
  goes back to unconfirmed. The revision is held per source in `projects_speaker_mappings` and
  compared in the `UPDATE` (or the first insert), so of two writers exactly one succeeds. Each
  assignment row also keeps the revision it was given at, and who gave it and when.
- **Linked automatically.** A label nobody answered links itself when exactly one participant
  someone already confirmed answers to it: one created as a speaker, or linked to any label,
  whose name is the label or who was linked to the same label in another transcript. Generic
  labels (`Speaker 1`, `Guest`, `Unknown`) never do, and the agent's reading alone never links
  one. Links are worked out on every read, so nothing is stored for them.
- **Never blocks a run.** Unconfirmed speakers are listed on People; the agent treats them as
  "role unknown".
- **Activity.** A save that changes something records `speakers.confirmed`, with counts only
  ("Confirmed who's who in a transcript: 2 speakers linked, 1 new participant, 1 not a
  person"), the source and each linked person as subjects.

### API

| Route                                          | Does                                           | Needs         |
| ---------------------------------------------- | ---------------------------------------------- | ------------- |
| `GET /projects/{id}/speakers`                  | Every current transcript's speakers and status | Any role      |
| `PUT /projects/{id}/sources/{source}/speakers` | Saves the whole answer for one transcript      | `editor` role |

`GET` returns `{"transcripts": [...]}` in source order, each with `source_id`,
`source_version_id`, `revision` (0 until the first save) and `speakers`: the label, its key, turn
count, first paragraph and sample from `sources`, plus `status` (`linked`,
`linked_automatically`, `not_a_person` or `unconfirmed`), `person_id`, `assigned_by` and
`assigned_at`. `GET /projects/{id}/people` adds `origin`, `entered_name`, `meeting_role`,
`spoke_in` (the transcripts a label is linked to them in) and `unconfirmed_speakers`.

`PUT` takes an `Idempotency-Key` and `{"expected_revision", "speakers": [...]}`. Each answer
has a `label_key` and a `choice`: `link` with `person_id` (and `meeting_role`: null keeps the
participant's, blank clears it), `new` with `name` and an optional `meeting_role`, or
`not_a_person`. Two labels may be linked to one participant, and two `new` answers with the same
name create one. It returns the transcript as `GET` lists it.

| Status | Code                     | When                                                                       |
| ------ | ------------------------ | -------------------------------------------------------------------------- |
| 403    | `PERMISSION_DENIED`      | A member without the `editor` role saves                                   |
| 404    | `NOT_FOUND`              | Not a member, or the source is another project's, removed or no transcript |
| 409    | `SPEAKERS_CHANGED`       | `expected_revision` is stale; `details.current_revision`                   |
| 409    | `PERSON_CHANGED`         | A linked participant changed while saving their meeting role               |
| 409    | `IDEMPOTENCY_KEY_REUSED` | The key was used for a different request                                   |
| 422    | `VALIDATION_ERROR`       | Body malformed, a name or meeting role over 80 characters, unknown choice  |
| 422    | `INVALID_INPUT`          | A blank name, an unknown label or person, a label answered twice, or two   |
|        |                          | meeting roles for one participant; `details.field` names the answer        |
| 422    | `PARTICIPANT_EXISTS`     | A new participant's name is a known person's; `details.person_id`          |

A retry with the same key returns the transcript as it is now. A save that changes nothing
keeps the revision and records nothing.

## Not here yet

- Goals, and stakeholder profiles beyond the people the sources name (P2 in the roadmap).
- Merging two people, or removing one; merging participants across projects.

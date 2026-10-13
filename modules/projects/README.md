# scopesteps-projects

Projects, goals, stakeholder profiles and decision rights.

Today the module holds projects themselves: listing the ones a user belongs to, creating one,
renaming it, and reporting the limits that apply to work in it. Memberships and roles belong to
`identity`, a project's scope status to `backlog` and the activity log to `audit`; this module
reaches them through their clients.

## Public interface

Other modules import only `scopesteps.projects.client`: `ProjectId`, and `ProjectRef` with the
`get_project_reader` dependency for showing a project's current name on versions and exports.
Everything else is internal and enforced by import-linter.

`client.py` stays free of SQLAlchemy because domain code in other modules imports `ProjectId`
from it. `get_project_reader` is therefore a FastAPI dependency the composition root binds
(`apps/api/.../main.py`), not a function that takes a session.

## What is where

| Path                           | Contains                                                         |
| ------------------------------ | ---------------------------------------------------------------- |
| `client.py`                    | `ProjectId`, `ProjectRef`, `get_project_reader`                  |
| `domain/project.py`            | `Project`, the name rule (`normalize_name`), the module's errors |
| `domain/limits.py`             | `ProjectLimits`, filled in by the composition root from settings |
| `application/projects.py`      | List, read, create and rename; the ports they need               |
| `infrastructure/orm.py`        | `projects_projects`, `projects_command_receipts`                 |
| `infrastructure/repository.py` | Projects with a revision-checked rename; command receipts        |
| `http/`                        | The routes below                                                 |

Tables are prefixed `projects_` (ADR 0003).

## API

| Route                  | Does                                                       | Needs              |
| ---------------------- | ---------------------------------------------------------- | ------------------ |
| `GET /projects`        | The actor's projects by name, with roles and status        | Signed in          |
| `POST /projects`       | Creates a project; the actor becomes its editor + approver | Signed in          |
| `GET /projects/{id}`   | One project with its roles, status and `limits`            | Any role on it     |
| `PATCH /projects/{id}` | Renames it                                                 | Editor or Approver |

`POST` takes `{"name"}` and returns 201. `PATCH` takes `{"name", "expected_revision"}`. Both need
an `Idempotency-Key` header, and both return the same body as `GET /projects/{id}`. The list
returns `{"projects": [...]}` with the same fields except `limits`.

| Field      | Meaning                                                                            |
| ---------- | ---------------------------------------------------------------------------------- |
| `roles`    | Every role the actor holds in the project, e.g. `["editor", "approver"]`           |
| `revision` | Starts at 1 and goes up with every rename; send it back as `expected_revision`     |
| `status`   | `state`, `baseline_version`, `baseline_version_id`, `open_version_id` (see below)  |
| `limits`   | `project_name_max_chars`, and `source`, `run` and `backlog` ceilings (detail only) |

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

## Rules

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
  key.
- **Status comes from `backlog`** (`load_scope_statuses`), derived from stored versions on every
  read; the whole list costs one query there. `state` is `candidate_in_review` or
  `draft_in_progress` while work newer than the current baseline is in flight, otherwise
  `baseline`, or `no_baseline` if nothing was ever approved. `baseline_version` (1 for the first
  approved version) and `baseline_version_id` are set whenever a baseline exists, and
  `open_version_id` names the candidate or draft the state refers to.
- **Limits are reported, not enforced, here.** `sources`, `agent` and `backlog` enforce them;
  the composition root copies the same settings and constants into `ProjectLimits`.
- The list is not paginated: a user's projects are few in the POC.

## Not here yet

- Goals, stakeholder profiles and decision rights (SSPOC-42).

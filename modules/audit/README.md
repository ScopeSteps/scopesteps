# scopesteps-audit

Append-only audit events for business actions, and the project activity feed that shows them.

## Public interface

Other modules import only `scopesteps.audit.client`. Everything else is internal and
enforced by import-linter.

| Name                                 | Is                                                                   |
| ------------------------------------ | -------------------------------------------------------------------- |
| `AuditRecorder`                      | The port a use case takes to record an event (`record(...)`)         |
| `audit_recorder(session)`            | The recorder that writes in that session's transaction               |
| `AuditActor`                         | Who acted: `AuditActor.user(actor)` or `AuditActor.agent()`          |
| `EventType`, `Subject`,`SubjectKind` | The vocabulary: what happened, and the ids of what it concerns       |
| `AuditEventId`                       | An event's id                                                        |
| `MAX_SUMMARY_CHARS`, `MAX_SUBJECTS`  | Limits a recorded event must fit; breaking one raises a `ValueError` |

### Recording an event

The use case takes an `AuditRecorder` next to its other ports and calls it where the action is
stored; the `http` layer (or the module's `client.py`) passes `audit_recorder(session)` built on
the same session as the repository.

```python
audit.record(
    project_id=version.project_id,
    actor=AuditActor.user(access.actor),
    type=EventType.BACKLOG_APPROVED,
    subjects=(Subject(SubjectKind.BACKLOG_VERSION, version.id),),
    summary=f"Approved baseline v{version.number}",
    occurred_at=now,
)
```

- The recorder never commits or flushes. The event is committed, or rolled back, with the action.
- Record an action that really happened: not an idempotent replay, not a refused command.
- `occurred_at` is the action's own time, the `now` the use case already has.
- `summary` is one printable line built from names, numbers and counts. Never put source text,
  a question, an answer, a credential or model output in it; the log is shown to every member.
- `subjects` are ids only. A reader that needs content asks the owning module, under its rules.

## Layout

| Path                           | Contains                                                        |
| ------------------------------ | --------------------------------------------------------------- |
| `client.py`                    | The recorder port, its session-bound implementation, vocabulary |
| `domain/event.py`              | `AuditEvent`, `AuditActor`, `Subject`, `EventType`, invariants  |
| `application/recording.py`     | `record_event`: the only write                                  |
| `application/feed.py`          | `list_activity`: one newest-first page, and the cursor encoding |
| `infrastructure/orm.py`        | `audit_events`, and the guard that refuses updates and deletes  |
| `infrastructure/repository.py` | Insert, and the keyset page query                               |
| `http/`                        | The activity feed route and its schemas                         |

Tables are prefixed `audit_` (ADR 0003).

## API

| Route                         | Does                                               |
| ----------------------------- | -------------------------------------------------- |
| `GET /projects/{id}/activity` | Lists the project's events, newest first, in pages |

Any role on the project may read it, and every member gets the same log. A project the actor has
no role in is `404 NOT_FOUND`, like one that does not exist.

| Query    | Meaning                                                                  |
| -------- | ------------------------------------------------------------------------ |
| `limit`  | Page size, 1 to 100; 50 when omitted                                     |
| `cursor` | The previous page's `next_cursor`; anything else is `422 INVALID_CURSOR` |

The response is `{"events": [...], "next_cursor": "..." | null}`; `next_cursor` is null on the
last page. Events are ordered by `occurred_at` then `id`, both descending. Pages are keyset pages:
the cursor is the position after the last event returned, so events recorded while a reader pages
never shift or repeat what follows.

An event:

```json
{
  "id": "019a3a5e-…",
  "project_id": "019a3a5e-…",
  "type": "source.added",
  "actor": { "kind": "user", "user_id": "019a3a5e-…", "display_name": "Local Reviewer" },
  "subjects": [
    { "kind": "source", "id": "019a3a5e-…" },
    { "kind": "source_version", "id": "019a3a5e-…" }
  ],
  "summary": "Added the brief brief.md (version 1)",
  "occurred_at": "2026-10-13T17:20:00.123456Z"
}
```

When the agent acted, `actor` is `{"kind": "agent", "user_id": null, "display_name": null}`.

## Event types

`EventType` is the whole vocabulary. Its values are stored and are part of the API contract: add
members, never rename or reuse one. A new type needs no migration.

Emitted today:

| Type                      | Actor | Emitted by | When                                                  |
| ------------------------- | ----- | ---------- | ----------------------------------------------------- |
| `source.added`            | user  | `sources`  | An upload creates a source version (one event each)   |
| `run.started`             | user  | `agent`    | A run is created                                      |
| `run.cancelled`           | user  | `agent`    | A run is stopped                                      |
| `clarification.requested` | agent | `agent`    | A step that asked the reviewer questions is committed |
| `clarification.answered`  | user  | `agent`    | A question is answered                                |
| `clarification.skipped`   | user  | `agent`    | A question is skipped                                 |
| `backlog.draft_saved`     | agent | `backlog`  | A run's candidate is saved as a draft version         |

Defined, and emitted by the ticket that builds the action:

| Type                                         | Emitted by |
| -------------------------------------------- | ---------- |
| `backlog.item_edited`                        | SSPOC-12   |
| `backlog.approved`, `backlog.rejected`       | SSPOC-12   |
| `suggestion.accepted`, `suggestion.rejected` | SSPOC-18   |
| `scope.decided`                              | SSPOC-18   |
| `change.approved`, `change.rejected`         | SSPOC-18   |
| `user.signed_in`, `user.signed_out`          | SSPOC-28   |
| `project.renamed`                            | SSPOC-31   |
| `source.removed`                             | SSPOC-34   |
| `person.corrected`                           | SSPOC-43   |

## Rules

- **Append-only.** The repository can insert and read, and nothing else; there is no route,
  use case or client function that changes or removes an event. The ORM refuses an update or a
  delete of a loaded event (`AuditEventImmutableError`). A bulk SQL statement or a database
  administrator is not stopped by that guard; a hosted deployment should also withhold `UPDATE`
  and `DELETE` on `audit_events` from the application's database role.
- **Same transaction.** An event exists exactly when its action was committed.
- **No content.** An event holds the project, the actor, a type, subject ids, the time and a
  summary of at most 200 characters on one line.
- **The actor's name is a copy** taken when they acted, so the log reads the same after a rename
  and the feed needs no lookup in `identity`.
- **Every event belongs to one project.** Sign-in and sign-out are not project actions; SSPOC-28
  decides how they reach a project's log (for example one event per project the user belongs to).

Recording is tested with in-memory fakes in `tests/`, and through the API and the database
(transactions, ordering, paging, permissions, the append-only guard) in
`apps/api/tests/test_activity.py`. The emitters are tested where their actions are:
`modules/sources/tests/test_upload_use_case.py` and `apps/api/tests/test_runs.py`.

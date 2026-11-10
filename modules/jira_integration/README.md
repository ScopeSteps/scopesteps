# jira_integration

One-way publishing of approved backlog versions to Jira Cloud
([ADR 0029](../../docs/adr/0029-one-way-jira-publishing-through-an-outbox.md)). It never
publishes a draft or a proposed version, never deletes in Jira, and reads approved content only
through `backlog.client`. Changes made in Jira do not come back (two-way sync is P3).

## Layout

- `domain/`: the connection and its Jira Cloud address and key rules (`connection.py`), the plan
  of what a publish does (`plan.py`, pure: epics, stories, then tasks, parent first; update only
  what changed; close what left), and publishes with their outbox entries (`publish.py`).
- `application/`: connecting, testing, auto-publish and disconnecting (`connections.py`);
  preview, start, advance, retry and the after-approval step (`publishing.py`); ports
  (`ports.py`).
- `infrastructure/`: tables (`orm.py`), `SqlJiraStore`, the Fernet token cipher (`crypto.py`),
  the REST v3 gateway over `httpx` (`jira_http.py`) and the backlog adapter (`versions.py`).
- `client.py`: `JiraRuntime` (cipher, gateway factory, app address) set at start-up, and
  `publish_after_approval`, which the composition root binds to `change_control`'s
  `get_after_approval`.

## Mapping

| ScopeSteps | Jira     | Fields                                                           |
| ---------- | -------- | ---------------------------------------------------------------- |
| Epic       | Epic     | Summary, description                                             |
| Story      | Story    | Summary, description, parent (its epic, when the version has it) |
| Task       | Sub-task | Summary, parent (its story)                                      |

The summary follows the CSV rule (`backlog.client.jira_summary`, ADR 0014). The description is
Atlassian Document Format: the item's text, then Acceptance criteria, Assumptions and Open
questions when there are any, then "Open in ScopeSteps" and the marker `ScopeSteps ID: <id>`
that finds an issue whose creation went unconfirmed. Issue types are read from the Jira project
when connecting (Epic by hierarchy level 1, Story by name, Sub-task by the `subtask` flag); a
project without all three is refused (`JIRA_PROJECT_UNSUITABLE`).

## API

All routes are under `/api/v1`. Approver means the `decide_versions` permission.

| Route                                        | Does                                                                 | Who      |
| -------------------------------------------- | -------------------------------------------------------------------- | -------- |
| `GET /projects/{id}/jira/connection`         | The connection without its token, and whether the server can connect | Approver |
| `PUT /projects/{id}/jira/connection`         | Tests site, email, API token and project key, then saves them        | Approver |
| `POST /projects/{id}/jira/connection/test`   | Checks the saved details still work                                  | Approver |
| `PATCH /projects/{id}/jira/connection`       | Turns automatic publishing on or off (revision-checked)              | Approver |
| `DELETE /projects/{id}/jira/connection`      | Deletes the connection and its token                                 | Approver |
| `GET /projects/{id}/jira/preview?version_id` | Create, update, close and unchanged counts; sends nothing            | Approver |
| `POST /projects/{id}/jira/publishes`         | Plans a publish of an approved version into the outbox               | Approver |
| `GET /projects/{id}/jira/publishes`          | The 20 newest publishes                                              | Approver |
| `GET /jira/publishes/{id}`                   | One publish, with its failed items                                   | Approver |
| `POST /jira/publishes/{id}/advance`          | Sends the next ten operations                                        | Approver |
| `POST /jira/publishes/{id}/retry`            | Sends a failed publish's failed items again                          | Approver |
| `GET /projects/{id}/jira/issues`             | The Jira key and link of each published epic, story and task         | Member   |

`POST .../publishes` takes an `Idempotency-Key`. A publish is `sending` until no entry is left
to send, then `done`, or `failed` when an item did not reach Jira; `failed` lists them with their
code. `last_error` says why an advance stopped early: `JIRA_RATE_LIMITED` or `JIRA_UNAVAILABLE`
(advance again later), or the code that failed the whole publish (`JIRA_AUTH_FAILED`,
`JIRA_FORBIDDEN`, `JIRA_NOT_CONNECTED`). An item fails alone with `JIRA_REJECTED` (Jira refused
its fields; `details` would name the fields, never Jira's message), `JIRA_NO_DONE_STATUS` (it
cannot be closed) or `PARENT_NOT_PUBLISHED`.

Errors: `409 JIRA_NOT_CONNECTED`, `VERSION_NOT_APPROVED`, `PUBLISH_IN_PROGRESS`,
`CONNECTION_CHANGED`, `PUBLISH_NOT_RETRYABLE`; `422 JIRA_SITE_INVALID`, `JIRA_AUTH_FAILED`,
`JIRA_PROJECT_NOT_FOUND`, `JIRA_PROJECT_UNSUITABLE`; `403 JIRA_FORBIDDEN`; `429
JIRA_RATE_LIMITED`; `502 JIRA_UNAVAILABLE`, `JIRA_REJECTED`; `503 JIRA_NOT_CONFIGURED`.

## Secrets

`JIRA_TOKEN_KEY` (a Fernet key) encrypts each project's API token in
`jira_integration_connections`. The token is accepted as a secret string, never returned,
logged, traced or put in an error; Jira's error bodies are not passed on, since they can echo
what was sent. A key that is not a Fernet key stops the API at start-up without printing it.

## Tests

`apps/api/tests/test_jira_publishing.py` runs every route against an in-process fake Jira Cloud
site (an `httpx.MockTransport`) that can refuse, rate-limit and lose answers;
`tests/test_plan.py` covers the plan, the address rules, the description and the cipher. No test
reaches the network. Trying it on a real site needs a separate Jira test project with synthetic
data, never SSPOC.

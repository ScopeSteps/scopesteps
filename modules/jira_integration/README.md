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

| ScopeSteps | Jira     | Fields                                                                                                        |
| ---------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| Epic       | Epic     | Summary, description                                                                                          |
| Story      | Story    | Summary, description, parent (its epic, when the version has it)                                              |
| Task       | Sub-task | Summary, parent (its story); on later publishes the summary only, so the team's notes in the description stay |

The summary follows the CSV rule (`backlog.client.jira_summary`, ADR 0014). The description is
Atlassian Document Format: the item's text, then Acceptance criteria, Assumptions and Open
questions when there are any, then "Open in ScopeSteps" and the marker `ScopeSteps ID: <id>`
that finds an issue whose creation went unconfirmed. Issue types are read from the Jira project
when connecting (Epic by hierarchy level 1, Story by name, Sub-task by the `subtask` flag); a
project without all three is refused (`JIRA_PROJECT_UNSUITABLE`).

## API

The web app's screens for these routes are in `apps/web/src/features/jira/`. All routes are
under `/api/v1`. Approver means the `decide_versions` permission. Publisher means
an approver, or an editor when the project's `publishers` setting is `approvers_and_editors`.

| Route                                        | Does                                                          | Who       |
| -------------------------------------------- | ------------------------------------------------------------- | --------- |
| `GET /projects/{id}/jira/connection`         | The connection (no token), `can_publish` and `can_manage`     | Member    |
| `PUT /projects/{id}/jira/connection`         | Tests site, email, API token and project key, then saves them | Approver  |
| `POST /projects/{id}/jira/connection/test`   | Checks the saved details still work                           | Approver  |
| `PATCH /projects/{id}/jira/connection`       | Turns automatic publishing on or off (revision-checked)       | Approver  |
| `DELETE /projects/{id}/jira/connection`      | Deletes the connection and its token                          | Approver  |
| `GET /projects/{id}/jira/preview?version_id` | Create, update, close and unchanged counts; sends nothing     | Publisher |
| `POST /projects/{id}/jira/publishes`         | Plans a publish of an approved version into the outbox        | Publisher |
| `GET /projects/{id}/jira/publishes`          | The 20 newest publishes                                       | Publisher |
| `GET /jira/publishes/{id}`                   | One publish, with its failed items                            | Publisher |
| `POST /jira/publishes/{id}/advance`          | Sends the next ten operations                                 | Publisher |
| `POST /jira/publishes/{id}/retry`            | Sends a failed publish's failed items again                   | Publisher |
| `GET /projects/{id}/jira/issues`             | The Jira key and link of each published epic, story and task  | Member    |

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

## The background sender

`send_due_publishes` (in `client.py`) is one round: it claims up to five due publishes, each
under a five-minute lease, and sends up to ten entries of each. `apps/api` runs it every five
seconds (`JIRA_PUBLISH_INTERVAL_SECONDS`) in a thread of the API process, or, with
`JIRA_PUBLISH_WORKER=separate`, leaves it to `scopesteps-jira-worker` in its own process. A rate
limit waits for `Retry-After`; an unreachable Jira backs off from 30 seconds to 15 minutes; an
item sent five times without an answer fails (`domain/publish.py`).

## The Jira account and its token

Connecting reads the account the token belongs to (`GET /myself`) and stores its name and id,
so Project settings can say "Connected as ScopeSteps Bot"; a dedicated account is recommended
([docs/product/jira-setup.md](../../docs/product/jira-setup.md)). The connection reports
`token_state`: `working`, `expires_soon` (14 days or less before the optional
`token_expires_on`), `expired` (that date has passed) or `rejected` (Jira answered 401: while
publishing, on a test, or in the background sender's daily `GET /myself`). Expired and rejected
stop publishing with `409 JIRA_TOKEN_EXPIRED` or `JIRA_TOKEN_REJECTED`, failing what was left of
a publish without calling Jira; a test or connection that works clears it, and Retry sends the
rest. The expiry date is checked: after today, at most 400 days ahead.

## Telling people

`infrastructure/notices.py` tells people through the notifications module, in the same
transaction as what happened (ADR 0029, note of 2026-11-11). When a publish ends, whoever started
it gets `jira_published` or `jira_publish_failed` with counts (created, updated, closed, failed,
sent, total); a failure is also emailed once, unless they turned that off. The daily token check
tells the project's approvers once when the token has 14 days or less left
(`jira_token_expiring`) and once when it stops working (`jira_token_stopped`); each state has a
stable key, so a new token starts afresh. The approvers come from identity's directory, which the
composition root hands to `jira_runtime`.

## Secrets

`JIRA_TOKEN_KEY` (a Fernet key) encrypts each project's API token in
`jira_integration_connections`. The token is accepted as a secret string, never returned,
logged, traced or put in an error; Jira's error bodies are not passed on, since they can echo
what was sent. A key that is not a Fernet key stops the API at start-up without printing it.

## Tests

`just jira-check` (`apps/api/.../jira_check.py`) is the live check against a real Jira test
project: run by a person, it asks for the token without echoing it, then creates, nests,
updates and closes three "[ScopeSteps check]" issues. It never runs in CI.

`apps/api/tests/test_jira_publishing.py` runs every route against an in-process fake Jira Cloud
site (an `httpx.MockTransport`) that can refuse, rate-limit and lose answers;
`tests/test_plan.py` covers the plan, the address rules, the description and the cipher. No test
reaches the network. Trying it on a real site needs a separate Jira test project with synthetic
data, never SSPOC.

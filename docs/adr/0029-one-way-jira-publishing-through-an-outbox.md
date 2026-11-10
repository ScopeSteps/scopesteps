# 0029. Approved versions are published one way to Jira Cloud through an outbox

- Status: Accepted
- Date: 2026-11-09

## Context

[ADR 0014](0014-jira-csv-export.md) left publishing straight to Jira for later: an approved
backlog reached Jira only as a CSV someone imported by hand. Release 1 brings publishing forward
from P1 (SSPOC-141). Sara decided on 2026-11-03: publishing is manual by default, with a
"Publish to Jira" button on an approved version and an "Also publish to Jira" checkbox in the
approve window, both unchecked by default; a project setting publishes automatically, off by
default; a preview always comes first; a later version updates the issues already published,
creates new ones and closes removed ones, never deleting; only the project's approver connects
Jira (Jira Cloud, an email and an API token), publishes and changes the setting; only approved
versions are ever published. Epics map to Epic, stories to Story and tasks to Sub-task, with the
acceptance criteria in the description and a link back.

Publishing calls an outside service many times for one version. A double click, a retry after a
lost response, two tabs or a server restart in the middle must never create an issue twice, and
a failure part way must be resumable. The app has no background worker: agent runs are advanced
one bounded step per request by the browser ([ADR 0005](0005-durable-agent-runs.md)).

## Decision

- **A new `jira_integration` module owns it**, with its own tables: the connection, publishes,
  their outbox entries and issue links (ScopeSteps item id to Jira key). It reads approved
  content only through `backlog.client`.
- **Jira Cloud only, by address.** The site must be `https://<name>.atlassian.net` (or
  `.jira.com`); anything else is refused before a request is made, so a project cannot point the
  server at internal hosts. Jira Server and Data Center are not supported.
- **The API token is encrypted at rest** with a Fernet key from settings (`JIRA_TOKEN_KEY`,
  AES with an HMAC). It is never returned, logged, put in an error, traced or sent to the model.
  Without the key, connecting is refused (`503 JIRA_NOT_CONFIGURED`). Changing the key makes
  saved tokens unreadable, so projects connect again. Connecting tests the details first.
- **Publishing goes through an outbox.** Starting a publish plans it (create, update, close per
  item, in parent-first order) and stores the plan as entries, in one transaction, sending
  nothing. Each `advance` sends up to ten entries. An entry is marked `sending` and committed
  before its Jira call, and `done` with the issue key after it. An entry still `sending` when an
  advance reaches it again has an unknown outcome: for a create, Jira is searched for the
  item's marker (`ScopeSteps ID: <id>`, written into every description) before creating. A start
  is idempotent by key, and a second start for the same version while one is sending returns it,
  so clicking twice publishes once.
- **The browser advances a publish**, as it does an agent run: no worker, and each request stays
  short. A rate limit or an unreachable Jira stops the advance early and keeps the rest for the
  next; an item Jira refuses fails alone (its children too), the rest go on, and a failed
  publish's retry sends only its failed entries.
- **Updates only when something changed.** Each link stores a fingerprint of what Jira was sent;
  an item whose fingerprint differs is updated, an unchanged one is left alone. An item a later
  version no longer has is moved to a done status, never deleted.
- **Approval stays first.** The approve request carries `also_publish_to_jira`. After the
  approval commits, a step `change_control` declares and the composition root binds starts a
  publish when asked or when the project publishes automatically. A refusal never undoes the
  approval: it comes back as `jira_problem`.
- **Approver only.** Connecting, testing, the setting, previews and publishes need
  `decide_versions`, the approver's permission; any member can see which issue each item became.
  Every connection change and every finished publish is in the activity log, with counts only.
- Moving a project to another Jira site or project forgets its issue links, so nothing is
  updated in the wrong place; disconnecting keeps them, so reconnecting the same project updates
  the same issues.

## Consequences

- Teams get their approved backlog into Jira in one click, kept in step with later versions,
  and the CSV export stays as the fallback.
- A publish moves only while a browser advances it. Closing the tab pauses it; it resumes from
  where it stopped. Auto-publish starts the publish, and the app advances it the next time an
  approver has the project open (SSPOC-143).
- The marker in every description is how an unconfirmed create is found again. Removing it in
  Jira means a crash in that narrow window could create the issue again.
- Changes made in Jira never come back (two-way sync stays in P3), and custom field mapping is
  not offered: summary, description and parent only.
- Tests use an in-process fake Jira; nothing is tested against a real site in CI. Trying it on a
  real site needs a separate test project with synthetic data, never SSPOC.

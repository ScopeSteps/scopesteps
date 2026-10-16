# Architecture overview

ScopeSteps is a **modular monolith** in a **monorepo**: one codebase, organized into bounded
contexts that are built like services but deployed together until there is a reason not to.
See [ADR 0001](../adr/0001-modular-monolith.md).

## Deployables

| App           | Technology                                                      | Runs as                                                    |
| ------------- | --------------------------------------------------------------- | ---------------------------------------------------------- |
| `apps/web`    | React, TypeScript, Vite, Tailwind, TanStack Query, React Router | Static SPA                                                 |
| `apps/api`    | FastAPI on Python 3.14                                          | HTTP API process                                           |
| `apps/worker` | Python (planned, P1)                                            | Background jobs for durable agent runs and Jira publishing |

Apps contain no business logic; they configure and compose modules. The API mounts only the
modules listed in `ENABLED_MODULES`.

## Web app

`apps/web` is one shell with a page per route. It holds no business rule: every id, state,
blocker and permission comes from the API, and the browser derives only presentation values
such as badge counts and the "next step" pill.

```text
apps/web/src/
  app/          Routes, pages and the shell (sidebar, top bar, settings) that frames them
  components/   Shared, feature-free building blocks: button, tag, card, modal, side sheet
  features/     One folder per backend module, each behind its index.ts
  lib/          The typed API client, error handling, browser preferences
  index.css     The design tokens, in light and dark, and their Tailwind mapping
```

- Pages import features only through their `index.ts`; features and pages build on
  `components/` and `lib/`. ESLint enforces both.
- The look follows the approved prototype, [docs/design/ScopeSteps-v1.html](../design/ScopeSteps-v1.html),
  which is a reference for layout, styling and wording, never for data or logic. Colours exist
  only as tokens; the Tailwind palette is switched off. Fonts are bundled, not fetched.
- The browser stores the theme, the accent, the sidebar state and the id of the last run it
  started, nothing else.
- The project in view is the id in the URL, so switching, refreshing and shared links all name
  it; the projects a user can switch to and their roles come from `GET /api/v1/projects`.
- A feature whose endpoint still returns 501 has no navigation item or control.

## Modules (bounded contexts)

| Module             | Responsibility                                                 | Subdomain  |
| ------------------ | -------------------------------------------------------------- | ---------- |
| `change_control`   | Baselines, change requests, scope diffs, approvals             | Core       |
| `backlog`          | Requirements, epics, stories, criteria, dependencies, versions | Core       |
| `evidence`         | Claims, evidence links, retrieval, citation validation         | Core       |
| `sources`          | Upload, validation, immutable source versions, source blocks   | Supporting |
| `agent`            | Harness, model providers, tools, runs, clarifications, limits  | Supporting |
| `projects`         | Projects and their limits, people and speakers, rights         | Supporting |
| `identity`         | Users, sign-in, sessions, memberships, roles, access checks    | Generic    |
| `audit`            | Append-only business audit events, project activity feed       | Generic    |
| `jira_integration` | Jira publishing and sync (P1)                                  | Generic    |
| `planning`         | Explicit-input estimates and scenarios (P2)                    | Supporting |

Core modules get full tactical DDD (aggregates, invariants, domain events). Generic modules stay
thin.

## Module structure and rules

```text
modules/<name>/src/scopesteps/<name>/
  client.py          Published IDs, DTOs and the functions or protocols other modules call.
  domain/            Entities, value objects, invariants, events. Pure Python.
  application/       Use cases and the ports (protocols) they depend on.
  infrastructure/    SQLAlchemy tables and repositories, external adapters.
  http/              FastAPI router, request/response schemas, dependencies.
```

Enforced in CI by import-linter (root `pyproject.toml`):

- Other modules may import only `client.py`. The API app, as composition root, may wire internals.
- Layers point inward: `http` → `infrastructure` → `application` → `domain`. `http` constructs
  adapters and passes them to use cases; infrastructure never imports `http`.
- `domain` and the kernel import no framework (FastAPI, Pydantic, SQLAlchemy). The check is
  transitive, so a `client.py` that domains import (`projects`, `identity`) stays framework-free
  too; it publishes a dependency the composition root binds instead of a function that takes a
  session.
- Modules and shared packages never import an app; shared packages import no module.

A module reaches another in one of two ways, both through `client.py`. A client that no domain
code imports may publish functions that take the caller's session (`backlog`, `sources`,
`evidence`, `change_control`). `identity` and `projects` publish the ids that other modules' domain code imports,
so their clients stay framework-free and publish FastAPI dependencies instead (`get_actor`,
`get_project_access`, `get_memberships`, `get_project_reader`, `get_people_recorder`), which the
composition root binds to the owning module's implementation with `app.dependency_overrides`.
Either way the call runs in the request's session, so it joins the caller's transaction.

The dependency runs the other way when a module must ask modules that build on it. Removing a
source is refused while anything refers to it, but runs, backlog versions and people live in
`agent`, `backlog` and `projects`, which import `sources`. So `sources.client` publishes
`get_source_usage_reader`, and the composition root binds it to a reader that asks each of them
(`apps/api/.../source_usage.py`); likewise `backlog` reads decisions from `change_control` through
`get_decision_reader`. Removal is soft and never deletes a stored version
([ADR 0009](../adr/0009-sources-of-any-kind-and-soft-removal.md)).

For example, the project list (`GET /projects`) is assembled by `projects` from three reads that
do not grow with the list: the actor's roles per project from `identity`, the project rows it
owns, and each project's scope status from `backlog`, which derives it from stored versions.
Creating a project writes the project row, the creator's editor and approver memberships
(through `identity`) and the idempotency receipt in one transaction.

Approving a draft is `change_control`'s use case on `backlog`'s versions. In one transaction it
reads the version's summary and runs the approval checks through `backlog.client` (which asks
`evidence` whether every citation resolves), freezes the version with a revision- and
hash-checked update, inserts the numbered approval that makes it the baseline, and records the
audit event ([ADR 0008](../adr/0008-atomic-baseline-approval.md)). Editing a draft and running
the checks without approving stay in `backlog`.

`change_control` records how each version was decided and builds on `backlog`, so `backlog`
cannot import it. `backlog` publishes the port instead (`get_decision_reader`), which the
composition root binds to `change_control`'s reader like the dependencies above. The version
history in `backlog` reads a page of version rows, then their decisions through that port.

Exporting an approved version is a read in `backlog`: it loads the frozen version, reads its
approval through that port and the project's name through `get_project_reader`, checks every
citation again through `evidence`, and renders JSON or Markdown. Drafts and rejected versions are
refused.

Shared packages: `packages/kernel` (IDs, domain errors and events; no dependencies) and
`packages/infrastructure` (database base, engine, HTTP dependencies).

## Data

SQLite locally, PostgreSQL when hosted ([ADR 0003](../adr/0003-sqlite-locally-and-table-prefixes.md)).
Each module owns the tables prefixed with its name (`identity_users`). One Alembic history in
`apps/api` migrates both dialects; CI runs it against Postgres. On SQLite, migrations run with foreign keys
off so batch table rebuilds succeed, then check for violations before re-enabling them. One database keeps the approval
transaction (freeze candidate → record approval and audit → move baseline) atomic.

## Audit events and activity

A module records a business action by calling `audit.client`'s `AuditRecorder` from the use case
that performs it, on the same database session, so the event is committed or rolled back with
the action. The recorder never commits. Events are append-only and content-free: project, actor
(a user or the agent), type, subject ids, time and a one-line summary built from names and
counts. Actions the agent takes on its own (asking questions, saving a draft) are attributed to
the agent, not to the reviewer who started the run. `GET /projects/{id}/activity` reads the log
newest first for any project member. The event types and who emits each are listed in the
[audit README](../../modules/audit/README.md).

## Model access and evaluation

Only the `agent` module talks to a model, through its `ModelProvider` port. Adapters exist per API
style (Gemini Interactions, OpenAI Chat Completions) and each provider has a profile with its
limits. Gemini is the primary; Groq is an opt-in backup a run may move to only before its first
successful call, so every run uses one model ([ADR 0004](../adr/0004-model-provider.md),
[ADR 0006](../adr/0006-groq-backup-provider.md)). Adapters never retry; callers do, with backoff.
Model output is untrusted until it passes the output schema, the deterministic draft checks and,
for scope, human approval. Every call emits one content-free trace event with OpenTelemetry GenAI
attribute names and an estimated cost.

Agent runs are durable rows advanced one bounded step per request, under a lease and a revision
check, with the model call made outside any transaction ([ADR 0005](../adr/0005-durable-agent-runs.md)).
A run pins any set of one or more source versions from sources the project has not removed.
The model can only read the run's pinned sources and ask the reviewer; code validates every
draft and decides every state change. Each call is stored as a content-free step with its usage
and estimated cost, and turn, token and cost limits are checked before it.

A finished draft leaves the agent module twice, in the transaction that marks the run ready: its
backlog goes to `backlog` as a draft version, and the people it names go to `projects`. The agent
reports a decision right only when a source states it and cites where; code keeps a person only
when a pinned paragraph they cite names them. `projects` stores that reading and, separately,
what people on the project change (a corrected name or role, a confirmed right, each with who and
when), so the agent's original is never overwritten and a later run cannot undo a correction.
Each correction and confirmation is revision-checked, takes an idempotency receipt in the same
`projects_command_receipts` table as project commands, and records its audit event in the same
transaction.

Who speaks in a transcript is found by a parser in `sources` when the version is stored, never by
a model, and read by other modules only through `sources.client` (ADR 0012). Editors answer for
each label in `projects`: a participant (created with a name and meeting role, or an existing
person) or not a person, kept per source with a revision. A run's reading of a person fills in a
participant with the same name and never overwrites what the editor entered.

Each project has one saved, append-only conversation with the agent, owned by `agent`. Runs write
their events, questions and answers into it; a free message starts a run in `reply` mode, which
takes one leased, budgeted step: a single model call with no tools that can only return claims
with citations. Code keeps a citation only when its quote is in the block it names and shows a
claim without one as the agent's own; a reply cannot change a draft, ask a question, start a run
or record a decision ([ADR 0010](../adr/0010-conversation-and-read-only-replies.md)). To read the
backlog and the project's current sources it calls `backlog.client` and `sources.client`, and a
changed clarification answer reaches the draft through `backlog.client`.

Once a baseline exists, scope changes through change requests
([ADR 0011](../adr/0011-change-requests-and-stable-id-change-sets.md)). `agent` takes the request
and, in one transaction, stores its text through `sources.client` (an immutable version the
change can cite), opens the change request through `change_control.client` against the baseline
id and hash the requester saw, and creates a change run. The run reads the baseline through
`backlog.client` under short labels; code checks its change set and maps it to stable ids, and
`backlog` builds the candidate by copying the baseline and applying only those operations, so the
approved version is never written. In the transaction that finishes the run, `agent` saves the
candidate (`in_review`) and reports the analysis to `change_control`, which counts the added,
changed and removed items from a stable-id comparison of the two versions. An approver then
records reverse or keep on each scope decision (a `backlog` command) and approves or rejects the
candidate with `change_control`'s decision use case: approval freezes it as the next baseline,
rejection leaves the baseline, and either moves the change request on in the same transaction.
That transaction also posts `change.approved` or `change.rejected` to the conversation:
`change_control` publishes a port (`get_change_outcome_recorder`) and the composition root binds
it to `agent`'s recorder, because `agent` already builds on `change_control` and the reverse
import would close a cycle. An approver answers a candidate's other open decisions (such as a
skipped clarification) with a `backlog` command, so a candidate need not be rejected for them.

`evals/` is a workspace package for measuring quality, not a deployable: annotated synthetic
packs (dev and frozen held-out), scoring, and its runners. It may import
`scopesteps.agent.client`, other modules' clients and `scopesteps.api.settings`; an
import-linter contract stops product code from importing it. See [evals/README.md](../../evals/README.md).

## Identifiers

UUIDs, typed per module with `NewType` so they cannot be mixed up. New IDs are UUIDv7
(time-ordered). Each module publishes its IDs in `client.py`:

| ID                                             | Owner          | Identifies                                                                       |
| ---------------------------------------------- | -------------- | -------------------------------------------------------------------------------- |
| `ProjectId`, `PersonId`                        | projects       | A project; a person named in its sources                                         |
| `UserId`                                       | identity       | A user                                                                           |
| `SourceId`, `SourceVersionId`, `SourceBlockId` | sources        | A document, an immutable version of it, a citable paragraph                      |
| `RunId`, `QuestionId`, `MessageId`             | agent          | An agent run, a clarification question, a message in the conversation            |
| `BacklogVersionId`, `ItemId`, `CriterionId`    | backlog        | A backlog version; an epic/story stable across versions; an acceptance criterion |
| `DecisionId`                                   | backlog        | A conflict or missing decision in a version: open, skipped or answered           |
| `EvidenceLinkId`                               | evidence       | A claim-to-passage link                                                          |
| `ApprovalId`, `ChangeSetId`, `ChangeRequestId` | change_control | An approve/reject decision; a proposed diff; a change request                    |
| `AuditEventId`                                 | audit          | A recorded business action                                                       |

## API contract

- Every route is under `/api/v1` and requires an authenticated actor, except sign-in and
  sign-out. `AUTH_MODE` picks where the actor comes from
  ([ADR 0007](../adr/0007-password-sign-in-and-server-side-sessions.md)):
  - `session` (the default): the user of the server-side session named by an HttpOnly cookie,
    started by `POST /api/v1/auth/sign-in` with an email and password. No session is a 401,
    which the web app answers by returning to its sign-in screen.
  - `local` (opt-in, for tests and scripted local work): the seeded reviewer, accepted only from
    loopback clients and only when `APP_ENV` is local or test.
- Requests that change data must carry a JSON body. A multipart upload or a request without a
  body is accepted only from the app's own origin or a non-browser client; form-encoded and
  plain-text bodies are refused (ADR 0007).
- Mutating commands require an `Idempotency-Key` header. Edits and approvals carry an expected
  revision; a stale one returns 409.
- A list that can grow without bound is paged by cursor: `limit` and an opaque `cursor` in, the
  items and a `next_cursor` (null on the last page) out, in a stable order with the id as the
  tie-breaker. The activity feed and the conversation use it.
- A project the actor has no role in is `404`, exactly like one that does not exist; a member
  without the role an action needs gets `403`.
- Limits the UI shows (source size and words, run turns, tool calls and clarification rounds,
  backlog size, project name length, message length) are reported by `GET /projects/{id}` from the deployment's
  settings; clients do not hard-code them.
- Errors share one envelope:
  `{"code", "message", "request_id", "retryable", "details"}`, and every response carries
  `X-Request-ID`.
- The OpenAPI schema is committed at `contracts/openapi.json`; `packages/api-client` types are
  generated from it, and CI fails when either is stale. Planned flows exist as routes returning
  `501 NOT_IMPLEMENTED` until built.

## Extracting a service later

When a module has a concrete reason to run separately (security isolation, different
availability or scaling needs), add `apps/<name>-api` that depends on that module, move its
tables to their own database, and swap callers' in-process `client.py` implementation for an HTTP
one. Record the decision in an ADR.

Full blueprint: [Technical Proposal](../proposals/ScopeSteps%20Technical%20Proposal.md).

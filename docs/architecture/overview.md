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

## Modules (bounded contexts)

| Module             | Responsibility                                                 | Subdomain  |
| ------------------ | -------------------------------------------------------------- | ---------- |
| `change_control`   | Baselines, change requests, scope diffs, approvals             | Core       |
| `backlog`          | Requirements, epics, stories, criteria, dependencies, versions | Core       |
| `evidence`         | Claims, evidence links, retrieval, citation validation         | Core       |
| `sources`          | Upload, validation, immutable source versions, source blocks   | Supporting |
| `agent`            | Harness, model providers, tools, runs, clarifications, limits  | Supporting |
| `projects`         | Projects, stakeholders, decision rights                        | Supporting |
| `identity`         | Users, memberships, roles, access checks                       | Generic    |
| `audit`            | Append-only business audit events                              | Generic    |
| `jira_integration` | Jira publishing and sync (P1)                                  | Generic    |
| `planning`         | Explicit-input estimates and scenarios (P2)                    | Supporting |

Core modules get full tactical DDD (aggregates, invariants, domain events). Generic modules stay
thin.

## Module structure and rules

```text
modules/<name>/src/scopesteps/<name>/
  client.py          Published IDs, DTOs and (later) the protocol other modules call.
  domain/            Entities, value objects, invariants, events. Pure Python.
  application/       Use cases and the ports (protocols) they depend on.
  infrastructure/    SQLAlchemy tables and repositories, external adapters.
  http/              FastAPI router, request/response schemas, dependencies.
```

Enforced in CI by import-linter (root `pyproject.toml`):

- Other modules may import only `client.py`. The API app, as composition root, may wire internals.
- Layers point inward: `http` → `infrastructure` → `application` → `domain`. `http` constructs
  adapters and passes them to use cases; infrastructure never imports `http`.
- `domain` and the kernel import no framework (FastAPI, Pydantic, SQLAlchemy).
- Modules and shared packages never import an app; shared packages import no module.

Shared packages: `packages/kernel` (IDs, domain errors and events; no dependencies) and
`packages/infrastructure` (database base, engine, HTTP dependencies).

## Data

SQLite locally, PostgreSQL when hosted ([ADR 0003](../adr/0003-sqlite-locally-and-table-prefixes.md)).
Each module owns the tables prefixed with its name (`identity_users`). One Alembic history in
`apps/api` migrates both dialects; CI runs it against Postgres. One database keeps the approval
transaction (freeze candidate → record approval and audit → move baseline) atomic.

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
The model can only read the run's pinned sources and ask the reviewer; code validates every
draft and decides every state change. Each call is stored as a content-free step with its usage
and estimated cost, and turn, token and cost limits are checked before it.

`evals/` is a workspace package for measuring quality, not a deployable: annotated synthetic
packs (dev and frozen held-out), scoring, and the single-pass baseline runner. It may import
`scopesteps.agent.client` and `scopesteps.api.settings`; an import-linter contract stops product
code from importing it. See [evals/README.md](../../evals/README.md).

## Identifiers

UUIDs, typed per module with `NewType` so they cannot be mixed up. New IDs are UUIDv7
(time-ordered). Each module publishes its IDs in `client.py`:

| ID                                             | Owner          | Identifies                                                                       |
| ---------------------------------------------- | -------------- | -------------------------------------------------------------------------------- |
| `ProjectId`                                    | projects       | A project                                                                        |
| `UserId`                                       | identity       | A user                                                                           |
| `SourceId`, `SourceVersionId`, `SourceBlockId` | sources        | A document, an immutable version of it, a citable paragraph                      |
| `RunId`, `QuestionId`                          | agent          | An agent run, a clarification question                                           |
| `BacklogVersionId`, `ItemId`, `CriterionId`    | backlog        | A backlog version; an epic/story stable across versions; an acceptance criterion |
| `EvidenceLinkId`                               | evidence       | A claim-to-passage link                                                          |
| `ApprovalId`, `ChangeSetId`                    | change_control | An approve/reject decision; a proposed diff                                      |

## API contract

- Every route is under `/api/v1` and requires an authenticated actor. Locally, the actor is the
  seeded reviewer, accepted only from loopback clients and only when `APP_ENV` is local or test.
- Mutating commands require an `Idempotency-Key` header. Edits and approvals carry an expected
  revision; a stale one returns 409.
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

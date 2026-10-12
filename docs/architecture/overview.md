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
  client.py          Public interface (protocol + DTOs). The only file other modules import.
  domain/            Entities, value objects, invariants, events. Pure Python.
  application/       Use cases and ports.
  infrastructure/    SQLAlchemy tables/repositories, external adapters.
  http/              FastAPI router and schemas.
```

Enforced in CI by import-linter (root `pyproject.toml`):

- Other modules may import only `client.py`.
- Layers point inward: `http` / `infrastructure` → `application` → `domain`.
- Modules and the kernel never import an app; the kernel imports no module.

## Data

One PostgreSQL instance with **one schema per module**. Modules reference each other's data by
ID, never by joining across schemas. Keeping one instance means the approval transaction
(freeze candidate → record approval and audit → move baseline) stays atomic.

## Contracts

The API's OpenAPI schema is committed at `contracts/openapi.json`. The frontend's types in
`packages/api-client` are generated from it, and CI fails when either is stale.

## Extracting a service later

When a module has a concrete reason to run separately (security isolation, different
availability or scaling needs), add `apps/<name>-api` that depends on that module, move its
schema to its own database, and swap callers' in-process `client.py` implementation for an HTTP
one. Record the decision in an ADR.

Full blueprint: [Technical Proposal](../proposals/ScopeSteps%20Technical%20Proposal.md).

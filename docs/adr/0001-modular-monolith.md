# 0001. Modular monolith with service-shaped modules

- Status: Accepted. Data decision superseded by [0003](0003-sqlite-locally-and-table-prefixes.md)
- Date: 2026-10-11

## Context

ScopeSteps has clear bounded contexts (sources, evidence, backlog, change control, agent, …) and
we want strong boundaries and the option to split services out later. It is built by a small team,
hosted on free tiers initially, and its central invariant is that approving a baseline is atomic:
freeze the candidate, record the approval and audit event, and move the baseline pointer, all in
one transaction.

Separate microservices with their own databases would turn that transaction into a distributed
saga, add network failure modes to every agent tool call, and multiply hosting cost.

## Decision

Build a modular monolith. Each bounded context is its own Python package with a public
`client.py`, internal layers, its own router, migrations and Postgres schema. All modules share
one PostgreSQL instance and are composed into a single API process; `ENABLED_MODULES` selects
which routers a process mounts. Boundaries are enforced by import-linter in CI.

A module is extracted into its own deployable only for a concrete reason (security isolation,
different availability or scaling needs, separate team ownership), recorded in a new ADR.

## Consequences

- Cross-module transactions remain possible and simple.
- Modules can be extracted later by swapping their `client.py` implementation for an HTTP client.
- One deployable to host and operate during P0–P1.
- Boundary discipline depends on the import-linter contracts staying complete as modules are added.

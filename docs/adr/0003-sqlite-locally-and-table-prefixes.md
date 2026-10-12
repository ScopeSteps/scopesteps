# 0003. SQLite locally, Postgres when hosted, table prefixes per module

- Status: Accepted
- Date: 2026-10-12
- Supersedes: the "Data" decision in [0001](0001-modular-monolith.md) (one Postgres schema per module)

## Context

The POC plan specifies local SQLite so the app runs without extra infrastructure. ADR 0001
assigned each module its own Postgres schema, which SQLite does not support. Hosted environments
still need Postgres.

## Decision

- Local development and tests use SQLite (`var/scopesteps.db`). Hosted environments use Postgres.
  CI runs every migration against both.
- Each module owns its tables through a name prefix: `<module>_<table>` (`identity_users`,
  `projects_projects`). A test fails if a mapped table lacks its module's prefix.
- One Alembic history for the whole database, shipped inside `apps/api`. Migrations are written to
  run on both dialects (batch mode for SQLite `ALTER`s).
- Foreign keys may reference another module's table so the database enforces integrity, but code
  never queries another module's tables; it goes through that module's `client.py`.
- Timestamps use `UtcDateTime`, which keeps values timezone-aware on SQLite.

## Consequences

- No Docker needed to run the app locally.
- Table ownership survives a later move to per-module Postgres schemas: the prefix maps directly
  to a schema name.
- SQLite-only behaviour (no concurrent writers, limited `ALTER`) must not be relied on; the
  Postgres CI job catches dialect drift.

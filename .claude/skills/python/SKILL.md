---
name: python
description: Conventions for writing or changing Python in ScopeSteps (modules/, packages/, apps/api, evals/). Use before writing, reviewing or refactoring any .py file, adding a module, endpoint, use case, repository, migration or pytest test.
---

# Python in ScopeSteps

Python 3.14, managed by uv. Read [CONTRIBUTING.md](../../../CONTRIBUTING.md) and
[docs/architecture/overview.md](../../../docs/architecture/overview.md) if you have not this
session; they are the source of truth and this skill only summarises them.

## Where code goes

Each module is `modules/<name>/src/scopesteps/<name>/` with five parts. Put code in the innermost
layer that can hold it.

| Layer             | Holds                                                    | May import                        |
| ----------------- | -------------------------------------------------------- | --------------------------------- |
| `domain/`         | Entities, value objects, invariants, domain errors       | stdlib, `scopesteps.kernel`       |
| `application/`    | Use cases as plain functions, ports as `Protocol`s       | `domain`, other modules' `client` |
| `infrastructure/` | SQLAlchemy tables (`orm.py`), repositories, API adapters | `application`, `domain`           |
| `http/`           | FastAPI router, request/response schemas, dependencies   | everything in its own module      |
| `client.py`       | IDs and DTOs other modules are allowed to use            | `scopesteps.kernel`               |

- Another module's `domain`, `application`, `infrastructure` or `http` is off limits. Import its
  `client.py`, or add what you need to that `client.py`.
- `identity.client` and `projects.client` are imported by other modules' domain code, so they
  stay free of SQLAlchemy: what they offer beyond types is a FastAPI dependency the composition
  root binds (`get_project_access`, `get_memberships`), not a function that takes a session.
- `domain/` and `packages/kernel` import no FastAPI, Pydantic or SQLAlchemy.
- `apps/api` wires modules together and holds no business logic.
- A module owns the tables prefixed with its name (`agent_runs`). Never query another module's
  tables.

`just boundaries` checks all of this; run it after adding an import across packages.

## Style

- Type hints on every function, including `-> None`. Pyright runs in strict mode: no `Any`
  leaking out, no untyped dicts where a dataclass fits, no `# type: ignore` without a reason.
- Domain and application values are `@dataclass(frozen=True)`; change them with
  `dataclasses.replace`. Pydantic models belong in `http/schemas.py` and at provider boundaries.
- Use cases are functions that take their ports as arguments
  (`get_user_profile(users: UserReader, actor: Actor)`). Define the port as a `Protocol` next to
  the use case that needs it; the `http` layer builds the adapter and passes it in.
- IDs are per-module `NewType`s over UUID, published in `client.py`. New IDs are UUIDv7 from the
  kernel. Never pass a bare `UUID` or `str` where a typed ID exists.
- Raise a `DomainError` subclass with a stable `code` and a message a user could read. Do not
  raise `HTTPException` below the `http` layer; the API maps domain errors to the error envelope.
- Modern syntax: `X | None`, `list[str]`, `collections.abc` for callables and iterables.
- Constants with a non-obvious value get a comment saying why that value (see the
  `code-comments` skill).

## Audit events

A use case that performs a business action a project member should see in the activity log takes
an `AuditRecorder` (`scopesteps.audit.client`) beside its other ports and records the event where
it stores the action; the `http` layer passes `audit_recorder(session)`. Never commit in between.
Summaries are built from names and counts, never from source text, answers or model output. Add
a new action to `EventType` and to the table in `modules/audit/README.md`.

## API changes

- Routes live under `/api/v1`, require an authenticated actor, and mutating routes take an
  `Idempotency-Key`. Edits and approvals carry an expected revision; a stale one is a 409.
- A list that can grow without bound is paged by cursor (`limit`, `cursor` → items,
  `next_cursor`), ordered with the id as the tie-breaker; see the activity feed in `modules/audit`.
- Mutating routes take a JSON body. A form-encoded or plain-text body is refused, and a
  multipart or body-less request is accepted only from the app's own origin (ADR 0007).
- In API tests, `make_client(url)` acts as the Local Reviewer; pass `auth_mode="session"` and
  sign in when the test is about who the user is (`apps/api/tests/test_session_auth.py`).
- After changing any route or schema run `just contract` and commit the regenerated
  `contracts/openapi.json` and `packages/api-client/src`.

## Database changes

1. Edit the module's `infrastructure/orm.py`.
2. `just migration "short description"`, then read the generated file. Autogenerate is a draft.
3. `just migrate && just test`. The migration must work on SQLite and Postgres.

Never edit a merged migration; add a new one.

## Tests

- pytest, in `<package>/tests/test_<thing>.py`. Arrange, act, assert, separated by blank lines.
- Name the behaviour: `test_local_auth_rejects_non_loopback_clients`, not `test_auth_2`.
- Use `pytest.mark.parametrize` when the same assertion runs over a table of cases.
- Test domain and application code with in-memory fakes of the ports. Use the API fixtures in
  `apps/api/tests/conftest.py` for HTTP behaviour. No test calls a real model or the network.
- Synthetic data only.

## Before you finish

Run `just format`, then `just check` (lint, pyright, boundaries, tests, migrations, contract).
Report what passed and what did not.

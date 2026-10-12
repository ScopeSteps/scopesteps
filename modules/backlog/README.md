# scopesteps-backlog

Requirements, epics, stories, acceptance criteria, dependencies and backlog versions.

## Public interface

Other modules import only `scopesteps.backlog.client`. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | `BacklogClient` protocol and the DTOs other modules use      |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router and request/response schemas                  |

Tables live in the `backlog` Postgres schema.

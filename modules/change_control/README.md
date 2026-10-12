# scopesteps-change-control

Approved baselines, change requests, scope diffs, approvals and rejections.

## Public interface

Other modules import only `scopesteps.change_control.client`. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                      |
| ----------------- | ------------------------------------------------------------- |
| `client.py`       | `ChangeControlClient` protocol and the DTOs other modules use |
| `domain/`         | Entities, value objects, invariants and events. Pure Python.  |
| `application/`    | Use cases and ports (repository/provider protocols)           |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters         |
| `http/`           | FastAPI router and request/response schemas                   |

Tables live in the `change_control` Postgres schema.

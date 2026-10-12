# scopesteps-change-control

Approved baselines, change requests, scope diffs, approvals and rejections.

## Public interface

Other modules import only `scopesteps.change_control.client`. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | Published IDs and DTOs other modules use                     |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router, request/response schemas, dependencies       |

Tables are prefixed `change_control_` (ADR 0003).

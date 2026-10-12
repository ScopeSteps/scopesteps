# scopesteps-agent

Agent harness: model providers, tools, run state, clarifications and usage limits.

## Public interface

Other modules import only `scopesteps.agent.client`. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | `AgentClient` protocol and the DTOs other modules use        |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router and request/response schemas                  |

Tables live in the `agent` Postgres schema.

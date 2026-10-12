# scopesteps-sources

Source upload and validation, immutable source versions and source blocks.

## Public interface

Other modules import only `scopesteps.sources.client`. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | `SourcesClient` protocol and the DTOs other modules use      |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router and request/response schemas                  |

Tables live in the `sources` Postgres schema.

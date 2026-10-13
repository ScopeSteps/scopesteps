# scopesteps-identity

Users, memberships, roles and project access checks.

## Public interface

Other modules import only `scopesteps.identity.client`. Everything else is internal and
enforced by import-linter.

The client publishes the ids, `Role`, `Actor` and `ProjectAccess`, and four FastAPI dependencies
that the composition root binds to this module's implementation:

| Dependency                    | Gives a route                                                    |
| ----------------------------- | ---------------------------------------------------------------- |
| `get_actor`                   | The signed-in user, for routes that address no project           |
| `get_project_access`          | The actor's roles in the `project_id` of the path                |
| `get_project_access_resolver` | The same for a project found from another resource               |
| `get_memberships`             | `Memberships`: a user's roles per project, and granting of roles |

`Memberships` performs no access check and writes in the request's transaction; `projects` uses
it to list a user's projects and to make a project's creator its editor and approver. Roles
combine and none implies another: `ProjectAccess.require_role` asks for one,
`require_any_role` for at least one of several.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | Published IDs and DTOs other modules use                     |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router, request/response schemas, dependencies       |

Tables are prefixed `identity_` (ADR 0003).

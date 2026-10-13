# scopesteps-identity

Users, password sign-in, server-side sessions, memberships, roles and project access checks.
The decisions are in
[ADR 0007](../../docs/adr/0007-password-sign-in-and-server-side-sessions.md).

## Who the actor is

`AUTH_MODE` selects how `get_current_actor` resolves the user a request acts for:

| Mode      | Actor                                            | Use                           |
| --------- | ------------------------------------------------ | ----------------------------- |
| `session` | The user of the session in the request's cookie  | Interactive use               |
| `local`   | The seeded Local Reviewer, loopback clients only | Tests and scripted local work |

Project access (`ProjectAccess.require_member`, `require_role`) is the same in both modes: it
reads the actor's memberships.

## Endpoints

| Route                        | Needs a session | Does                                                          |
| ---------------------------- | --------------- | ------------------------------------------------------------- |
| `POST /api/v1/auth/sign-in`  | No              | Checks `{email, password}`, starts a session, sets the cookie |
| `POST /api/v1/auth/sign-out` | No              | Ends the presented session and clears the cookie; always 204  |
| `GET /api/v1/me`             | Yes             | The current user and their project roles                      |

- Sign-in returns the same body as `/me`. Every failure is `401 INVALID_CREDENTIALS` with one
  message. Under `AUTH_MODE=local` it is `503 SIGN_IN_DISABLED`.
- A request without a valid session gets `401 UNAUTHENTICATED`, whether the session is missing,
  expired or signed out.
- The session token exists only in the cookie; `identity_sessions` stores its SHA-256.
  `identity_users.password_hash` holds an Argon2id hash, or null for an account that cannot
  sign in.

## Accounts

`just seed` creates the Local Reviewer and one account per role on the demo project:
`viewer@scopesteps.local`, `editor@scopesteps.local` and `approver@scopesteps.local`. Set
`SEED_ACCOUNT_PASSWORD` in `.env` and re-run the seed to give them a password; without it they
exist but cannot sign in. There is no registration, password reset or admin command.

To try session mode locally:

```sh
# in .env: AUTH_MODE=session and SEED_ACCOUNT_PASSWORD=<your own, 12+ characters>
just seed
just api
```

## Not built yet

- **Sign-in and sign-out are not audited.** The audit vocabulary defines `user.signed_in` and
  `user.signed_out`, but nothing emits them. This is an open follow-up that needs a team
  decision, not just wiring: every audit event must name a project (`audit_events.project_id`
  is not nullable) and a sign-in belongs to none, and `audit` already depends on this module's
  client, so identity cannot simply call it.
- Rate limiting, password reset and change, self-registration and single sign-on (ADR 0007).

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

Tables are prefixed `identity_` (ADR 0003): `identity_users`, `identity_memberships`,
`identity_sessions`.

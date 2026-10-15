# scopesteps-identity

Users, password sign-in, server-side sessions, memberships, roles and project access checks.
The decisions are in
[ADR 0007](../../docs/adr/0007-password-sign-in-and-server-side-sessions.md).

## Who the actor is

`AUTH_MODE` selects how `get_current_actor` resolves the user a request acts for:

| Mode      | Actor                                            | Use                                       |
| --------- | ------------------------------------------------ | ----------------------------------------- |
| `session` | The user of the session in the request's cookie  | The default; interactive use              |
| `local`   | The seeded Local Reviewer, loopback clients only | Opt-in, for tests and scripted local work |

Project access (`ProjectAccess.require_member`, `require_role`) is the same in both modes: it
reads the actor's memberships.

## Endpoints

| Route                               | Needs a session | Does                                                          |
| ----------------------------------- | --------------- | ------------------------------------------------------------- |
| `POST /api/v1/auth/sign-in`         | No              | Checks `{email, password}`, starts a session, sets the cookie |
| `POST /api/v1/auth/sign-out`        | No              | Ends the presented session and clears the cookie; always 204  |
| `GET /api/v1/me`                    | Yes             | The current user and their project roles                      |
| `PATCH /api/v1/me`                  | Yes             | Updates the current user's profile; email and roles stay      |
| `GET /api/v1/projects/{id}/members` | Yes             | The project's members by name, with job title and roles       |

- Sign-in returns the same body as `/me`. Every failure is `401 INVALID_CREDENTIALS` with one
  message. Under `AUTH_MODE=local` it is `503 SIGN_IN_DISABLED`.
- A request without a valid session gets `401 UNAUTHENTICATED`, whether the session is missing,
  expired or signed out.
- A profile is a name (1 to 60 characters), a job title (up to 80) and about text (up to
  280), counted after trimming. The name and title are one line; about keeps line breaks.
  Invalid input is `422 PROFILE_INVALID` naming the field. The update carries
  `expected_revision` from `/me`; a stale one is `409 PROFILE_CHANGED`. Sending the stored
  profile again succeeds without a new revision, so a retry is safe without an
  `Idempotency-Key`.
- The member list omits email addresses. A user who is not a member gets `404`, as for every
  project route.
- The session token exists only in the cookie; `identity_sessions` stores its SHA-256.
  `identity_users.password_hash` holds an Argon2id hash, or null for an account that cannot
  sign in.

## Accounts

`just seed` creates the Local Reviewer and one account per role on the demo project:
`viewer@scopesteps.local`, `editor@scopesteps.local` and `approver@scopesteps.local`. They get
the password in `SEED_ACCOUNT_PASSWORD`; `just setup` generates one in a local `.env` that has
none (`python -m scopesteps.api.local_env`) and leaves a value you set alone. Change it in `.env`
and re-run `just seed`. Without it the accounts exist but cannot sign in. There is no
registration, password reset or admin command.

The web app's sign-in screen and sign-out use the two endpoints above; see
`apps/web/src/features/README.md`.

## Not built yet

- **Sign-in and sign-out are not audited.** The audit vocabulary defines `user.signed_in` and
  `user.signed_out`, but nothing emits them. This is an open follow-up that needs a team
  decision, not just wiring: every audit event must name a project (`audit_events.project_id`
  is not nullable) and a sign-in belongs to none, and `audit` already depends on this module's
  client, so identity cannot simply call it.
- **Profile changes are not audited**, for the same reason as sign-in: a profile belongs to no
  project. SSPOC-49 asks for the event once the audit module exists; it waits on the same
  decision.
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

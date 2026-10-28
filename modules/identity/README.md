# scopesteps-identity

Users, sign-up, password sign-in, server-side sessions, memberships, roles, invitations and
project access checks. The decisions are in
[ADR 0007](../../docs/adr/0007-password-sign-in-and-server-side-sessions.md) (sign-in and
sessions) and [ADR 0019](../../docs/adr/0019-accounts-invitations-and-project-roles.md) (sign-up,
invitations and member roles).

## Who the actor is

`AUTH_MODE` selects how `get_current_actor` resolves the user a request acts for:

| Mode      | Actor                                            | Use                                       |
| --------- | ------------------------------------------------ | ----------------------------------------- |
| `session` | The user of the session in the request's cookie  | The default; interactive use              |
| `local`   | The seeded Local Reviewer, loopback clients only | Opt-in, for tests and scripted local work |

Project access (`ProjectAccess.require_member`, `require_role`) is the same in both modes: it
reads the actor's memberships.

## Endpoints

| Route                                                | Needs a session | Does                                                          |
| ---------------------------------------------------- | --------------- | ------------------------------------------------------------- |
| `POST /api/v1/auth/sign-in`                          | No              | Checks `{email, password}`, starts a session, sets the cookie |
| `POST /api/v1/auth/sign-out`                         | No              | Ends the presented session and clears the cookie; always 204  |
| `GET /api/v1/me`                                     | Yes             | The current user and their project roles                      |
| `PATCH /api/v1/me`                                   | Yes             | Updates the current user's profile; email and roles stay      |
| `GET /api/v1/projects/{id}/members`                  | Yes             | The project's members by name, with job title and roles       |
| `POST /api/v1/auth/sign-up`                          | No              | Creates an account that waits for its email to be confirmed   |
| `POST /api/v1/auth/verify-email`                     | No              | Confirms the email from the link's token and starts a session |
| `POST /api/v1/auth/resend-verification`              | No              | Sends a new confirmation link; always the same `202`          |
| `GET /api/v1/invitations/{token}`                    | No              | Who invited the person to which project, as which roles       |
| `POST /api/v1/invitations/{token}/sign-up`           | No              | Creates the invited account, joins and starts a session       |
| `POST /api/v1/invitations/{token}/accept`            | Yes             | Joins the project as the signed-in, invited account           |
| `POST /api/v1/projects/{id}/members`                 | Yes             | Invites an email with roles; approver only                    |
| `GET /api/v1/projects/{id}/invitations`              | Yes             | Invitations nobody accepted yet; approver only                |
| `POST /api/v1/projects/{id}/invitations/{inv}/link`  | Yes             | A new link; the old one stops; approver only                  |
| `POST /api/v1/projects/{id}/invitations/{inv}/email` | Yes             | Emails a new link; approver only                              |
| `DELETE /api/v1/projects/{id}/invitations/{inv}`     | Yes             | Cancels an invitation; approver only                          |
| `PUT /api/v1/projects/{id}/members/{user}/roles`     | Yes             | Replaces a member's roles at their revision; approver only    |
| `DELETE /api/v1/projects/{id}/members/{user}`        | Yes             | Removes a member (approver), or leaves (your own id)          |

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
- The member list omits email addresses and gives each member's `revision`, which a role change
  sends back as `expected_revision`. A user who is not a member gets `404`, as for every project
  route.
- The session token exists only in the cookie; `identity_sessions` stores its SHA-256.
  `identity_users.password_hash` holds an Argon2id hash, or null for an account that cannot
  sign in.

## Sign-up, invitations and members

The rules are in [ADR 0019](../../docs/adr/0019-accounts-invitations-and-project-roles.md). In
short:

- Sign-up and resend always answer `202` with the same body. A weak password is `422`
  (`INVALID_INPUT`, with `min_length` and `max_length`), a malformed email `422 EMAIL_INVALID`,
  and too many attempts `429 RATE_LIMITED`: 5 an hour per client address, 3 per email.
- An unconfirmed account's sign-in with the right password is `403 EMAIL_NOT_VERIFIED`. A
  confirmation link that is unknown, used or older than 24 hours is `404 TOKEN_INVALID`.
- An invitation link that is unknown, used, replaced, cancelled or older than 7 days is
  `404 INVITATION_INVALID`. Accepting it as another account is `403 INVITATION_EMAIL_MISMATCH`.
  Signing up from it when the email has a confirmed account is `409 ACCOUNT_EXISTS`.
- Inviting a member is `409 ALREADY_MEMBER`, and inviting an email with an open invitation is
  `409 ALREADY_INVITED` (`details.invitation_id`). Roles must be a non-empty choice of viewer,
  editor and approver (`422`). An approver sends at most 20 invitation emails an hour.
- Only approvers invite, list, re-link, email, cancel, change roles and remove (`403` for others).
  Any member leaves with `DELETE .../members/{their own id}`. The last approver cannot leave, be
  removed or lose the role: `409 LAST_APPROVER`. A stale role change is `409 MEMBER_CHANGED`.
- Emails are sent after the transaction commits (`application/emails.py`, through the
  `EmailSender` port; `infrastructure/email.py` has the SMTP adapter and an in-memory one for
  tests). An approver's failed send is `502 EMAIL_FAILED`; an invitation whose first email failed
  returns its link to copy instead (`email_sent: false`).
- Each project action records one event through the `get_member_activity` port, which the
  composition root binds to `audit` (`member.invited`, `invitation.link_created`,
  `invitation.emailed`, `invitation.accepted`, `invitation.cancelled`, `member.roles_changed`,
  `member.removed`, `member.left`), with display and role names only. Refused actions record
  none. Sign-up is logged without the address.
- These routes keep their own state instead of an `Idempotency-Key`: a repeated invitation is
  `409 ALREADY_INVITED`, a repeated role change carries a stale revision, and a repeated removal
  finds no member.

In development the API sends email over SMTP to the local Mailpit inbox (`just mail`, read it at
http://localhost:8025). The settings are `APP_BASE_URL`, `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME` and `SMTP_PASSWORD` in `.env.example`.

## Accounts

`just seed` creates the Local Reviewer and one account per role on the demo project:
`viewer@scopesteps.local`, `editor@scopesteps.local` and `approver@scopesteps.local`. They get
the password in `SEED_ACCOUNT_PASSWORD`; `just setup` generates one in a local `.env` that has
none (`python -m scopesteps.api.local_env`) and leaves a value you set alone. Change it in `.env`
and re-run `just seed`. Without it the accounts exist but cannot sign in. Seeded accounts count
as confirmed. Anyone else signs up (above). There is no password reset or admin command.

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
- Password reset and change, single sign-on, CAPTCHA, and the workspace and integration admin
  roles (ADR 0019).

## Public interface

Other modules import only `scopesteps.identity.client`. Everything else is internal and
enforced by import-linter.

The client publishes the ids, `Role`, `Actor`, `ProjectAccess`, `MemberEvent` and
`MemberActivity`, and five FastAPI dependencies that the composition root binds:

| Dependency                    | Gives a route                                                            |
| ----------------------------- | ------------------------------------------------------------------------ |
| `get_actor`                   | The signed-in user, for routes that address no project                   |
| `get_project_access`          | The actor's roles in the `project_id` of the path                        |
| `get_project_access_resolver` | The same for a project found from another resource                       |
| `get_memberships`             | `Memberships`: a user's roles per project, and granting of roles         |
| `get_member_activity`         | `MemberActivity`, bound to `audit`'s recorder (it builds on this module) |

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
`identity_sessions`, `identity_member_revisions`, `identity_email_tokens`,
`identity_invitations` and `identity_attempts`.

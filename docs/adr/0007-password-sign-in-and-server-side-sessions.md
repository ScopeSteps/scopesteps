# 0007. Password sign-in with server-side sessions

- Status: Accepted
- Date: 2026-10-13

## Context

Until now every request acted as one seeded reviewer (`AUTH_MODE=local`), so the platform could
not say who answered, edited or approved. The roadmap had hosted authentication in P1; on
2026-10-13 sign-in and sign-out were moved into the POC (SSPOC-27). The POC runs locally with
synthetic accounts, so the decision has to be safe by default without the cost of an identity
provider, and must not block the frontend, whose sign-in screen (SSPOC-29) is built after the
backend (SSPOC-28).

The web app and the API share one origin (the Vite proxy locally). One existing route, the source
upload, takes `multipart/form-data`; every other mutating route takes JSON or no body.

## Decision

**Two authentication modes, chosen by `AUTH_MODE`.**

- `session`: the actor is the user of the session named by the request's cookie. Allowed in
  every environment.
- `local`: every request acts as the seeded Local Reviewer. Still refused outside
  `APP_ENV=local`/`test` and a loopback `API_HOST`, and still accepted from loopback clients
  only. Sign-in answers `503 SIGN_IN_DISABLED` in this mode. The Local Reviewer has no password
  and can never sign in.
- **The default stays `local` until SSPOC-29 merges**, because the web app has no sign-in screen
  yet and would be unusable. SSPOC-29 flips the default in `Settings` and `.env.example` to
  `session`. After that `local` is an explicit opt-in kept for the API test suite and scripted
  local work; it is not a production feature and cannot be enabled there.

**Accounts.** Accounts are created by the seed only: one synthetic account per role (viewer,
editor, approver) on the demo project. Their shared password comes from `SEED_ACCOUNT_PASSWORD`
in the local `.env`; `.env.example` ships it empty and no password is committed. When it is
unset, the seed still creates the accounts but gives them no password, says so, and they cannot
sign in. When it is set, re-running the seed makes it the accounts' password. It must be 12 to
1024 characters; there is no complexity rule. Emails are stored and compared lower-cased.

**Passwords.** Stored only as Argon2id hashes made by `argon2-cffi` with its default parameters
(the RFC 9106 low-memory profile), each with its own salt. A hash made with older parameters is
replaced at the next successful sign-in. An unknown email, an account without a password and a
wrong password all verify against a hash (a dummy one when there is none) and return the same
`401 INVALID_CREDENTIALS` body. Passwords are never logged or returned; validation errors no
longer echo the submitted input.

**Sessions.**

- The token is 32 random bytes from the operating system, sent only in the cookie. The server
  stores its SHA-256, so a database leak exposes no usable session.
- Absolute lifetime 12 hours and idle timeout 2 hours (`SESSION_ABSOLUTE_LIFETIME_MINUTES`,
  `SESSION_IDLE_TIMEOUT_MINUTES`, validated at start-up). Activity is recorded at most once a
  minute so reads do not each become a write.
- Sign-in always issues a new token and ends the session the client presented, so a token set
  before sign-in is never adopted. Sign-out deletes the session row. Expired rows are removed at
  the next sign-in.
- A user may hold several sessions (one per browser); signing out ends only the presented one.

**Cookie.** `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain`, `Max-Age` equal to the absolute
lifetime. Outside `APP_ENV=local`/`test` it is also `Secure` and named
`__Host-scopesteps_session`, which browsers accept only over HTTPS for that exact host. Locally
it is `scopesteps_session`, because a `__Host-` cookie cannot be set over plain HTTP.

**Cross-site requests.** No CSRF token. Instead, for every request that is not `GET`, `HEAD` or
`OPTIONS`:

1. An `application/json` body is accepted. Another origin cannot send that content type without a
   CORS preflight, and only `CORS_ALLOWED_ORIGINS` pass it.
2. Any other body type except multipart (form-encoded, `text/plain`, …) is refused with `415`.
   These are what an HTML form on another site can send.
3. A multipart body, or no body, is accepted only when the `Origin` header is one of
   `CORS_ALLOWED_ORIGINS` or matches the request's own `Host`. A request with neither `Origin` nor
   a cross-site `Sec-Fetch-Site` header is a non-browser client, which has no ambient cookie, and
   is accepted. Anything else is refused with `403 CROSS_SITE_REQUEST`.

The ticket's wording is "mutating requests accept only JSON bodies". Rule 3 is the deliberate
exception that keeps the source upload working without a rewrite: a multipart upload is
exactly the request a cross-site form could forge, so it is the one that must prove its origin.
The same check covers body-less commands (sign-out, advancing or cancelling a run), which a JSON
rule alone would not. `SameSite=Lax` is not enough by itself: another port on `localhost` is the
same site.

**Endpoints.** `POST /api/v1/auth/sign-in` and `POST /api/v1/auth/sign-out` are the only
`/api/v1` routes reachable without an actor. They take no `Idempotency-Key`: repeating a sign-in
only starts another session, and repeating a sign-out is a no-op.

## Out of scope

Decided for the POC, to revisit before any hosted use:

- **Rate limiting and lockout** on sign-in. Argon2 makes each guess slow; nothing limits their
  number.
- **CSRF tokens.** Replaced by the cross-site rules above.
- **Password reset and change, self-registration, an admin command for accounts.**
- **Single sign-on** stays in P1.
- **Audit events for sign-in and sign-out.** The audit vocabulary defines `user.signed_in` and
  `user.signed_out`, but they are not emitted: every audit event must name a project
  (`audit_events.project_id` is not nullable) and these actions have none. Open follow-up; it
  needs a decision on events without a project before any wiring.
- Ending a user's other sessions, and a scheduled clean-up of expired rows.

## Consequences

- Role checks are unchanged: they read the actor, which now comes from the session.
- The web app must be served from the API's origin (the Vite proxy locally). CORS stays without
  credentials, so a page on another origin cannot use the cookie.
- Until SSPOC-29 flips the default, a fresh checkout still runs as the Local Reviewer, and
  session mode is opt-in: set `AUTH_MODE=session` and `SEED_ACCOUNT_PASSWORD`, then `just seed`.
- Every authenticated request reads one session row; at most one write a minute per session.
- A new non-JSON mutating route works only from a trusted origin. Prefer JSON.
- Raising Argon2 parameters needs no migration; hashes upgrade as people sign in.

## Notes added 2026-10-14 (default flipped with the sign-in screen)

The decision is unchanged; the step it planned has happened.

- The sign-in screen and sign-out are built (SSPOC-29), and `AUTH_MODE` now defaults to
  `session` in `Settings` and `.env.example`. `local` is an explicit opt-in. The API test client
  still sets it, so tests that are not about who the user is keep acting as the Local Reviewer.
- No password is committed still. `just setup` writes a random `SEED_ACCOUNT_PASSWORD` into a
  local `.env` that has none, and never replaces one that is set, so a fresh checkout has
  accounts that can sign in. The value is not printed; it stays in `.env`.
- An existing `.env` copied from the old `.env.example` still says `AUTH_MODE=local`. That keeps
  working as before; delete the line to sign in. `just setup` points this out.
- The web app treats any `401` other than a refused sign-in as the end of the session: it returns
  to sign-in with the page to come back to, and drops every cached response. Signing out does the
  same once the API has ended the session.

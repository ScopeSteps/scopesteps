# 0019. Open sign-up, invitations by link or email, and project roles managed by approvers

- Status: Accepted
- Date: 2026-10-27

## Context

Until now accounts came only from the developer seed command, only a project's creator ever got
roles (editor and approver), the members list was read-only and the POC sent no email
([ADR 0007](0007-password-sign-in-and-server-side-sessions.md) left registration out). People
need to create their own account, approvers need to bring others into a project with chosen
roles, and members need to be able to leave. Roles are already per project and combine, and
every action checks them.

## Decision

**Accounts.** Anyone can sign up with a name, an email and a password (the existing length rules).
The answer is always the same `202`, so it never reveals whether the address has an account: a
new address gets a confirmation link, and an address with a confirmed account gets an email
saying so, with a sign-in link. An account signs in only once its address is confirmed
(`403 EMAIL_NOT_VERIFIED`, given only after the password matched). A sign-up for an address nobody
has confirmed replaces that account's name and password, because no one has proven they own it.
Accounts that existed before are counted as confirmed. A new account has no projects. It can
create its own (becoming its editor and approver, as before), and an invitation is the only way
into someone else's project.

**Links.** Confirmation and invitation links carry a random 256-bit token. Only its SHA-256 is
stored, and the raw token is returned or emailed once and never logged. The server's access log
redacts the invitation token in its path. A confirmation link works once for 24 hours, and asking
again replaces it. An invitation link works once, for the invited email only, and for 7 days
from when it was made. Making a new link or cancelling the invitation stops the old one, since only
the newest hash is kept. Unknown, expired, used, replaced and cancelled links all get the same
`404`.

**Invitations.** Every invitation has a personal link, whether or not the email has an account.
The approver can have ScopeSteps email it, copy it to share another way, or both. Opening it with
the invited account joins the project (sign in first if needed). Opening it without an account
offers a short form that creates the account already confirmed, joins and signs in, in one
step: the link proves the address. Another signed-in account is refused and asked to switch. A
copied link works for whoever opens it within these rules, so it must be shared privately; the
approver sees who joined and can remove them.

**Roles.** Approvers manage members: invite, change roles, remove. Editors and viewers cannot,
so nobody can promote themselves. Only viewer, editor and approver are granted from the app, and
a new person gets Viewer unless the approver picks more. Any member can leave. A project always
keeps an approver. The last one cannot leave, be removed or lose the role
(`409 LAST_APPROVER`). This is checked inside the transaction with the project's approver
memberships locked (`SELECT ... FOR UPDATE` on Postgres) and counted again after the write, so
two approvers acting at once cannot leave none, even on SQLite, which does not lock rows. A role
change carries the member's revision (`409 MEMBER_CHANGED` when stale). Leaving or removal deletes
the memberships only. Access ends on the next request, and what the person wrote keeps their
name.

**Limits.** Sign-ups and confirmation resends are limited to 5 an hour per client address and 3
an hour per email. An approver may send 20 invitation emails an hour (`429 RATE_LIMITED`).
Attempts are stored with hashed keys, so the limits hold across processes and restarts.

**Email.** Emails go through an `EmailSender` port with one SMTP adapter, so choosing Postmark,
Resend or Amazon SES is a settings change. In development the settings point at a local Mailpit
inbox and nothing reaches a real person. Use cases only build messages, and the HTTP layer sends
them after the transaction commits. A failed sign-up email is logged without the address or link
and the answer stays the same. An approver's failed send returns `502 EMAIL_FAILED`. An invitation
whose first email failed still stands, and its link is returned to copy. Messages name the
inviter, the project, the roles, the link and its expiry, with names escaped, and carry nothing
else from the project.

**Audit.** Every invitation, new link, email sent, acceptance, cancellation, role change, removal
and leave is recorded in the project's activity log in the action's transaction. Summaries use
display names and role names, never an email address or a token. `audit` builds on identity's
client, so identity publishes a port (`get_member_activity`) that the composition root binds to
the audit recorder. Sign-up belongs to no project and is only logged, without the address.

## Consequences

- People can join without a developer. Approvers decide who sees, edits or decides on their
  projects.
- Invitation links are bearer secrets within their rules, so sharing one is sharing access to
  that project as those roles, until it is used, replaced, cancelled or expires.
- Going live needs the email service chosen and the sending domain verified (SPF and DKIM).
  Postmark (about $15 a month for 10,000 emails, best inbox delivery) is recommended, and Resend
  (free up to 3,000 a month) is cheaper to start. Check the providers' prices before deciding.
- The client address used for the per-address limit is the direct peer. Behind a proxy it must be
  the forwarded address, which needs trusted-proxy settings before deployment.
- Password reset, sign-in with Google or Microsoft, CAPTCHA and the workspace and integration
  admin roles stay out of scope.

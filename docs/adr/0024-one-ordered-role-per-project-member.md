# 0024. One ordered role per project member, checked as named permissions

- Status: Accepted
- Date: 2026-11-04

## Context

[ADR 0019](0019-accounts-invitations-and-project-roles.md) kept the POC's roles: Viewer, Editor
and Approver, held per project, combinable, with none implying another. That left combinations
that make no sense for a real team. Someone invited only as Approver, usually the person who
signs off the scope, could not chat with the agent, upload a source or edit the backlog. A
project's creator always held two roles. And every module checked role names directly
(`require_role(Role.EDITOR)`), so what a role allowed was spread over seven modules and the web
app guessed it again from role names.

## Decision

**Roles.** Each member holds exactly one role per project: Viewer, Editor or Approver, in that
order. Each role can do everything the roles below it can:

| Role     | Can do                                                                                                               |
| -------- | -------------------------------------------------------------------------------------------------------------------- |
| Viewer   | Read the project and take part in discussions (start, reply, close their own)                                        |
| Editor   | Viewer, plus sources, people and speakers, the agent, the backlog, change requests, closing any discussion, renaming |
| Approver | Editor, plus approving or rejecting versions and suggestions on a draft, and managing members                        |

A person can hold a different role on each project. The workspace and integration admin roles
are never held in a project and grant nothing there.

**Permissions.** What each role may do is decided in one place: `identity.client` maps every
`Permission` to the lowest role that has it. Modules check a permission
(`access.require(Permission.EDIT_BACKLOG)`), never a role name. A refusal names the roles that
may (`403`, `details.required_role`). A non-member still gets the same `404` as for a project that
does not exist. The project responses and `GET /me` give the user's role and permissions in each
project, and the web app shows controls from the permissions.

**Approving.** An Approver may approve or reject a version they edited, drafted or requested
themselves. There is no four-eyes rule (decided by Sara, 2026-11-04).

**Membership rules.** As in ADR 0019: approvers invite, change roles and remove members; any
member may leave; a project always keeps an approver (`409 LAST_APPROVER`, now also when the last
approver lowers their own role). An invitation carries one role. The creator of a project
becomes its Approver.

**Existing data.** A migration keeps each member's highest role, so nobody loses access: Editor
and Approver together become Approver. Invitations keep their highest role the same way.

## Consequences

- One person can run a small project from start to sign-off, which matches how the app is used
  today. A team that wants a second pair of eyes on approval has to agree it among themselves
  until a four-eyes setting exists.
- Adding a permission, or moving one to another role, is a change to one table plus its tests;
  modules and the web app follow it.
- `PUT /members/{user}/role` takes one `role`, and the invitation and member responses carry
  `role` instead of `roles`. This is a breaking change to the API contract, made together with
  the web app.
- Roles that change over time and company-wide admin roles stay out of scope.

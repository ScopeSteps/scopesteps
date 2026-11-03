# 0021. Mentions, following and notifications, with batched emails sent by a background job

- Status: Accepted
- Date: 2026-10-31

## Context

[ADR 0020](0020-discussions-as-their-own-module.md) left mentions and notifications out. A
question in a discussion only helps if it reaches the right person, and they have no reason to
open the Discussion page to find it. Decided 2026-10-26 (Sara), following Slack, Jira, GitHub and
Google Docs.

Notifications are not about discussions alone in the long run, and they need their own reads,
settings and retention. Emails also raise something new: until now every email was sent by the
request that caused it, but a batch per person and thread has to go out when nobody is making a
request.

## Decision

**A separate module.** `notifications` owns notifications, email choices and email windows
(`notifications_*` tables). It knows nothing of comments: it holds ids, and reads names through
`identity.client`, `projects.client` and `backlog.client`. `discussions` decides who is told and
calls `notifications.client` in the comment's transaction, so a rolled-back comment tells nobody.

**Mentions.** A body stores `<@user_id>`, and responses add each person's current name, so a rename
updates old mentions. Only current members can be mentioned (`422 MENTION_NOT_MEMBER`). An edit
checks only the mentions it adds, so a comment may keep naming someone who has left.

**Following.** Starting, commenting in or being mentioned in a thread follows it, and any member
may follow it by hand. A person who unfollows stays out until they follow again: commenting does
not undo it. A mention still reaches them, without following them back in.

**Who is told.** A mention tells the person mentioned. A reply tells followers who are still
members. Someone mentioned in a reply gets one notification, the mention. Nobody is told about
their own comment. An edit tells only people it newly mentions, and each person hears once about a
comment however often a mention is taken out and put back. Deleting a comment withdraws what it
caused.

**Reading.** Each person sees only their own, and only for projects they are a member of now.
Leaving hides them rather than deleting them. The app checks every 30 seconds while the tab is
visible; live push is out of scope. Notifications are kept for 90 days.

**Email.** A person gets mention emails by default and reply emails only if they ask, and at most
one email per thread every 15 minutes. The first goes out on the next tick; what arrives inside
the window waits and goes out as one batch when it ends, unless it was read, the person changed
their choice or they left the project. A message names who, the item, the project and a link,
never comment text (the rule of [ADR 0019](0019-accounts-invitations-and-project-roles.md)). A
batch is claimed by moving the person's window for the thread and committing, then sent. A send
is retried once, and a failure is logged by kind, without the address. The email is then dropped
and the in-app notification stands, so an email is sent at most once.

**A background job.** One daemon thread per API process (`apps/api`) ticks every 30 seconds, sends
what is due and clears expired notifications once a day. It needs no new infrastructure, which
suits a POC. Several processes are safe, because a batch is claimed by compare-and-set.

**The email port moves to the kernel.** `EmailSender`, `EmailMessage` and the shared layout were in
`identity`; a second module now sends email, so they live in `scopesteps.kernel.email`.

## Consequences

- A person hears about what needs them without watching the page, and the data model stays
  content-free outside the comment itself.
- A failed email is not retried after its one retry, and a process that stops between the claim
  and the send loses that email. The bell still shows the notification.
- The job runs only while the API runs. A deployment with no API process sends nothing, and one
  that scales to zero delays emails.
- Mentions of groups, people outside the project, mobile push and Teams or Slack delivery are left
  out; each needs its own decision.

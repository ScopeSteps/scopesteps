# 0020. Discussions are their own module and never reach the agent on their own

- Status: Accepted
- Date: 2026-10-30

## Context

Teams talk about scope outside meetings: in corridors, direct messages and quick calls. None of
it reaches a transcript, so ScopeSteps never sees it. Project members need a place inside the
project to write that talk down, next to the epic or story it is about, or in a General
discussion when it is about no item yet. Decided 2026-10-26 (Sara), following the comment
threads of Jira, Google Docs, Notion and GitHub.

Two things make comments unlike anything the app stores today. They are half-formed ideas that
were never meant as decisions, and they are free text from any member, viewers included, which
makes them a prompt-injection path if a model reads them.

## Decision

**A separate module.** `discussions` owns threads and comments (`discussions_*` tables). It reads
item names and the current backlog version through `backlog.client` and writes activity through
`audit.client`; nothing builds on it yet, and its client publishes only its ids.

**What a thread is.** A thread belongs to one epic or story, by the item id that `backlog` keeps
across versions, or to the project's General discussion. It is a first comment and its replies,
one level deep, oldest first. Each comment records the backlog version in flight, or else the
baseline, when it was written. A thread on an item later removed from the backlog stays readable
and says so.

**Who may do what.** Every member reads, starts threads and replies. Only an author edits (shown
as edited) or deletes (soft: the text is gone, the row stays) their comment. The thread's author,
an editor or an approver resolves it; anyone reopens it, and a resolved thread takes no reply
until then. Non-members get the same 404 as everywhere. Each comment keeps its author's name as
written, so people who leave keep their name on it.

**A comment is never a decision.** No discussion endpoint changes the backlog, a scope decision
or an approval. Turning a discussion into a scope change is a person's step, through a change
request (SSPOC-114).

**Never sent to the agent on its own.** No prompt, tool or lookup reads discussions. Comment text
reaches a model only when a person puts it into a change request or a message.

**Content-free activity.** Starting, resolving and reopening a thread are recorded as
`thread.started`, `thread.resolved` and `thread.reopened`, naming the item, never the comment
text. Replies, edits and deletions are not logged. A member may post at most 30 comments a
minute in a project (`429 RATE_LIMITED`).

**Plain text.** Comments are 1 to 5,000 characters of plain text, trimmed and stored as written.
The web app escapes them and makes web addresses clickable; nothing is rendered as HTML.

## Consequences

- Talk outside meetings has a home, and none of it can change scope or reach the agent by itself.
- The agent cannot learn from discussions until a person sends one on, which costs a step but
  keeps half-formed ideas and injected instructions out of drafts.
- Mentions and notifications (SSPOC-111), attachments, reactions, comments on single acceptance
  criteria and importing from Teams or Slack are left out; each needs its own decision.

## Notes

2026-10-31: Two things this record left open are built, and no rule above changed.

- Mentions and notifications are decided in
  [ADR 0021](0021-mentions-followers-and-notifications.md). `notifications` is a new module, and
  `discussions` now tells it who needs to hear about a comment.
- A person can send a discussion as a change request. The server builds a quote of the thread, the
  person edits it, and only what they submit reaches the agent, as an ordinary change request read
  as untrusted source text. The thread and the request are linked in
  `discussions_change_requests`, and `thread.sent_as_change_request` is recorded without any text.
  `discussions` now reads request status through `change_control.client`, and `agent` builds on
  `discussions.client`. Change requests made from a thread are open to Approvers as well as
  Editors, and such an Approver can advance, answer and stop that change run, because otherwise it
  would wait for an Editor. Typed change requests still need the Editor role, and a change still
  needs an Approver's decision.

# 0013. A reply may suggest one next step, which a person takes

- Status: Accepted
- Date: 2026-10-16

## Context

A conversation reply can only explain ([ADR 0010](0010-conversation-and-read-only-replies.md)).
When a reviewer writes "please raise that as a change request" or answers an open decision in a
message, they then have to find the right screen and type it again. SSPOC-55 (decided
2026-10-16) lets a reply carry a suggestion the reviewer can take with one click.

That widens what a reply produces, so it must not widen what a reply can do: the agent's safety
rests on the model proposing and code and people deciding (the `agent-harness` skill).

## Decision

- **One typed suggestion at most, of three kinds.** Under prompt `reply-v3` (schema `reply.v3`,
  `reply-v2` plus a `suggestion` field) a reply may suggest something a person already does in
  the app: submit a change request (`request_text`), answer an open backlog decision (its label
  and the answer), or start a draft run. No other kind exists in the schema.
- **Code decides whether it is offered.** A suggestion is kept only when the project could take
  that step now: a change request needs a baseline and no candidate in review, an answer needs an
  open decision that takes a written answer (not a scope reversal) in a draft or candidate, and a
  draft run needs current sources. Texts must be valid messages, and an answer must be copied
  from the reviewer's own message, so neither the model nor a source can put words in the
  reviewer's mouth. A suggestion that fails is dropped, never repaired; the reply is kept, and the
  step records the code (`suggestion_dropped`), never the text.
- **Storing it runs nothing; a person acts through the existing endpoint.** A kept suggestion is
  stored with its reply in `agent_suggestions`, with status `offered`. To take it, the client
  calls the endpoint a person already uses (a `change_request` message, the backlog's decision
  answer, run creation), which repeats every role, revision, baseline and busy check, and then
  records `accepted` with `PUT /projects/{id}/messages/{message_id}/suggestion`; `dismissed` is
  recorded the same way. The status changes once, from `offered`, with a revision check, by an
  editor or approver. Messages stay append-only: the status lives beside the message.
- **The next reply sees what happened.** Earlier replies' suggestions and their status reach the
  model as data in the conversation, so a dismissed one is not offered again unprompted.
- **Adopted only once measured.** New reply runs keep their pinned prompt (`reply-v1`) until
  `reply-v3` is measured against it on the dev reply questions, after asking.

## Consequences

- A reply still cannot change state. The worst a bad suggestion can do is show a card a person
  ignores or dismisses.
- Accepting is two requests (the action, then the status). If the second fails, the card still
  shows `offered` although the action happened; the action's own idempotency and checks make a
  repeat harmless, and the thread shows the action's result.
- The status route is idempotent by state, so it takes an `Idempotency-Key` but keeps no receipt.
- Dev reply questions gain `suggest` expectations, so suggestions are scored, not only counted.

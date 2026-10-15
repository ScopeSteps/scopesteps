# 0010. A saved conversation, with one read-only reply run per message

- Status: Accepted
- Date: 2026-10-14

## Context

A reviewer works with the agent in one place: they ask where something came from, answer its
clarification questions and, once a baseline exists, request changes. Until now the API stored no
conversation: the only thing a person could send the agent was an answer to a run's question, and
the chat screen rebuilt its thread from the current run's state, so it was lost with the next run.

The agent's safety rests on two rules that a free-text channel could erode: the model proposes and
application code decides (the `agent-harness` skill), and every model call is a bounded, leased,
budgeted step of a durable run ([ADR 0005](0005-durable-agent-runs.md)). A message is untrusted
text, like a source, and a reply that sounded authoritative without evidence would undo the
provenance the drafts are built on.

A fuller design, where the agent could ask questions or start work from the conversation, was
considered and set aside for the POC: it needs a new agent loop and new evaluation, and the
backlog's questions already come from runs.

## Decision

- **One conversation per project, append-only.** `agent_messages` holds every message in order
  (time, then id), with its role (`user`, `agent`, `system`), kind (`message`, `change_request`,
  `reply`, `question`, `answer`, `skip`, `answer_changed`, `event`), author and the author's name
  as it was when written, and links to the run and the question it belongs to. Nothing is edited
  or deleted. `GET /projects/{id}/messages` pages it newest first by cursor and returns the
  current state of each question it mentions and the work in progress, if any. Every member reads
  the same thread; posting needs the editor role.
- **Runs write to the thread.** Starting, finishing, failing and stopping a run, its questions, and
  each answer, skip or changed answer add a message in the transaction that stores the action. A
  message holds no step, prompt or trace content.
- **A free message starts one reply run.** `POST /projects/{id}/messages` stores the message and
  creates a run in `reply` mode in one transaction; the client advances it with the existing
  `POST /runs/{id}/advance` and stops it with `POST /runs/{id}/cancel`. A reply run is a durable
  run: it pins the project's current source versions, its model and prompt, and the deployment's
  run limits when it is created, and it takes the lease, the revision check and the budget and
  project cost checks every step takes. It ends `completed`, `failed` or `cancelled`, never
  `ready_for_review`. Stopping keeps the message and any saved progress; there is no resume.
- **A reply can only produce text.** Its one step is one model call with no tools and a JSON
  output schema (`reply.v1`): at most 6 short claims, each with citations of a source block
  (`B1..`) or a recorded answer (`A1..`). Code keeps a citation only when its quote is found in the
  block it names, and a claim with no citation left is stored and shown as the agent's own
  (`basis: agent`), as draft checks already treat unsupported claims. A reply cannot change a
  draft, ask or answer a question, start a run, approve anything or record a decision; asked to,
  it says that a person does that.
- **What a reply reads.** The pinned source paragraphs, every answered clarification question of
  the project's runs, the newest backlog version in flight or else the baseline (titles,
  descriptions, criteria and open decisions, without evidence), and up to 10 earlier messages and
  replies, each cut to 1,000 characters. All of it is escaped inside tags and declared data, never
  instructions (prompt `reply-v1`).
- **One piece of conversation work at a time.** A message is refused with retryable
  `409 AGENT_BUSY`, naming the run, while any run in the project is created or running; a run
  waiting for answers does not block it. A run cannot start while a reply is created or running.
  Both take the project's turn (`agent_conversation_turns`, compare-and-set), so two requests sent
  at once cannot both start work.
- **Limits.** A message is 1 to 2,000 characters after trimming, with no control or invisible
  characters, checked by the server and published as `limits.conversation.max_message_chars` by
  `GET /projects/{id}`. A reply's output, claims and citations are cut in code rather than
  refused, so an over-long reply is shortened, not lost.
- **Cost.** A reply costs one model call. Its steps count towards the project's cost and its
  limit like any run's, and appear in the activity log as `message.sent` and `message.replied`
  (counts only).
- **Answers stay changeable until approval.** An answered or skipped question can be changed,
  with the run's revision, while its round is open or once the run's draft is saved; the draft
  then moves to its next revision. Once that version is approved or rejected, or while the agent
  is using the answers, the change is refused (`409 ANSWER_LOCKED`, `409 RUN_STATE_INVALID`).
- **Change requests hand off to change analysis.** A message sent as `change_request` needs an
  approved baseline (`409 BASELINE_REQUIRED`). It will start a change run against the current
  baseline; until change analysis exists it is refused with `501` and nothing is stored.

## Consequences

- The thread survives new runs and reloads, and the frontend renders it from one paged endpoint
  instead of rebuilding it from run state.
- Replies reuse everything runs already guarantee: content-free traces and steps, budgets,
  leases, idempotency receipts and the backup-provider rules. No new loop, tool or approval path
  exists, so the model gains no way to change state.
- A reply's quality is not proven by the schema alone. Its prompt is measured on reply questions
  in the dev packs (`just evals-reply`, [evals/README.md](../../evals/README.md)); it has not been
  measured live yet.
- A reply is not cheap context: it sends the whole pinned source text with every message. On the
  dev packs a request is about 1.9K to 2.9K estimated tokens before backlog and conversation; a
  project near the source word limit sends far more, and on a provider with a small per-request
  allowance it fails before sending as `request_too_large` rather than being cut.
- Reply runs do not count as pinning a source: a source cited only by replies can still be
  removed, and its passages stay readable by id (ADR 0009).
- A changed answer updates the draft's decision, but criteria the draft wrote from the earlier
  answer are not rewritten; the reviewer edits them or starts a new run.
- Change requests are stored as messages only once change analysis lands; until then a
  `change_request` leaves no trace in the thread.

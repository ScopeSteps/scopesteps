# scopesteps-agent

Agent harness: model providers, drafting, draft checks, budgets, tracing and cost estimates,
durable agent runs with tools and clarification ([ADR 0005](../../docs/adr/0005-durable-agent-runs.md)),
and the project's conversation with read-only, cited replies
([ADR 0010](../../docs/adr/0010-conversation-and-read-only-replies.md)).

How to change it safely: the `agent-harness` skill in `.claude/skills/` and
[ADR 0004](../../docs/adr/0004-model-provider.md). Quality is measured in
[evals/](../../evals/README.md).

## Public interface

Other modules and `evals` import only `scopesteps.agent.client`: `create_model_provider`,
`draft_single_pass`, `check_draft`, the draft schemas and version constants, `trace_scope`,
`estimate_cost_usd`, `AgentRuntime`, `RunLimits`, `MAX_MESSAGE_CHARS`, and `run_offline` and
`reply_offline` for evaluations. Everything else is internal and enforced by import-linter.
`http/router.py` also has `resolve_change_outcome_recorder`, which the composition root binds to
`change_control`'s `get_change_outcome_recorder`, so a decided change is posted to the thread
without `change_control` importing this module.

## What is where

| Path                                            | Contains                                                                         |
| ----------------------------------------------- | -------------------------------------------------------------------------------- |
| `domain/model.py`                               | Provider-neutral requests, results, tool calls, usage and `ModelProviderError`   |
| `domain/budget.py`                              | Run limits and counters; `check_can_call` before every model call                |
| `domain/pricing.py`                             | Paid-tier price table and cost estimates (thinking billed as output)             |
| `domain/providers.py`                           | `ProviderProfile`: per-provider defaults, free-tier limits, quirks               |
| `domain/rate.py`                                | `TokenWindow`: pacing to a tokens-per-minute allowance                           |
| `domain/run.py`                                 | Run, question and step records; statuses, stages, lease                          |
| `domain/conversation.py`                        | Messages, claims and citations; the message limit and its checks                 |
| `application/ports.py`                          | The `ModelProvider` protocol: one provider, no retries, no fallback              |
| `application/schemas.py`                        | Typed draft output and tool arguments; the JSON schema sent to providers         |
| `application/drafting.py`                       | Versioned prompts and single-pass drafting with one bounded repair               |
| `application/checks.py`                         | Deterministic draft checks (citations, open decisions, stories, people)          |
| `application/candidate.py`                      | A checked draft becomes the `backlog` candidate and the `projects` people        |
| `application/naming.py`                         | Request labels (B3, S2) in the model's prose replaced by the names people see    |
| `application/tracing.py`                        | `trace_scope` attributes for content-free traces                                 |
| `application/runs.py`                           | Run use cases: create, get, advance (leased step), answer, change, cancel        |
| `application/conversation.py`                   | Post a message (starts a reply run) and page the thread                          |
| `application/replying.py`                       | Prompts `reply-v1` to `reply-v4`, their schemas, resolving a reply's citations   |
| `application/suggestions.py`                    | Whether a `reply-v3` suggestion may be offered (ADR 0013)                        |
| `application/reply_tools.py`                    | A reply's read-only lookups: `lookup_source`, `get_story`, `list_open_decisions` |
| `application/change_requests.py`                | Submit a change request: the request, its text and its change run, one commit    |
| `application/changing.py`                       | Prompts `change-v1`, `change-v2`, schema `change-set.v1`, checks, stable ids     |
| `application/speakers.py`                       | The escaped `speakers` attribute and the rules change and reply prompts add      |
| `application/offline.py`                        | A run, a reply or a change analysis in memory, with the same steps, for evals    |
| `application/steps.py`                          | One bounded step: explore with tools, draft or change set and repair, or reply   |
| `application/fallback.py`                       | Opt-in backup at run start and the circuit breaker (ADR 0006)                    |
| `application/tools.py`                          | `lookup_source`, `request_clarification`, `validate_backlog`                     |
| `infrastructure/orm.py`                         | Runs, steps, questions, receipts, `agent_messages`, the conversation turn        |
| `infrastructure/repository.py`                  | Compare-and-set run writes, step ledger, pinned passages from `sources`          |
| `infrastructure/providers/gemini.py`            | Gemini Interactions adapter: `store=False`, SDK retries off, errors classified   |
| `infrastructure/providers/openai_compatible.py` | OpenAI Chat Completions adapter (Groq, ADR 0006): no retries, strict schemas     |
| `infrastructure/providers/groq.py`              | Groq profile (backup provider)                                                   |
| `infrastructure/providers/paced.py`             | Waits for the per-minute token allowance (probes and evaluations only)           |
| `infrastructure/providers/traced.py`            | One OpenTelemetry GenAI-named event per call, success or failure                 |
| `infrastructure/providers/fake.py`              | Scripted provider for tests                                                      |
| `http/`                                         | Run routes (create, get, advance, answers, cancel) and the conversation          |

Runs draft with prompt `draft-v7` (schema `draft-backlog.v4`): `draft-v6`, which is `draft-v4`
with the people the sources name, plus who speaks in each transcript paragraph as people on the
project confirmed it (ADR 0012). Neither `draft-v6` nor `draft-v7` has been measured live yet (see
[evals/README.md](../../evals/README.md)); `draft-v1` to `draft-v6` stay available with the
schemas, checks and requests they were measured with. There is no `draft-v5`: that name belongs to
an experiment that was measured and not adopted.

Confirmed speakers: when a run advances, `SqlPassageReader` gives each transcript paragraph that
holds speech its speakers, in order: the turns come from `sources.client.load_speaker_turns` (the
parser, never source text read here) and who each label is from `projects.client`'s
`SpeakerIdentityReader`. `draft-v7` shows them in an escaped `speakers` attribute ("Dana: Dana
Ruiz, Sponsor", "Sam: role unknown", "Guest 1: not a person"), which the prompt declares data.
The people check and `to_people` accept a cited turn by a speaker confirmed under that name as
naming them; `to_people` keeps the confirmed name and the participant's id, so the reading is
stored on that participant and never renames them, and drops a label marked not a person.
Change and reply runs read the same passages. `change-v2` and `reply-v4` show the same attribute
and add the rules in `speakers.py`, which also say to quote only the text inside a tag, never an
attribute; a change set quoting the attribute gets a check message that says so, for its repair.
Neither is adopted yet: new runs pin `change-v1` and `reply-v3` until the new versions are
measured live, and earlier versions render their requests as before.

A run pins any set of one or more source versions, each once, from sources the project has not
removed (`422 INVALID_INPUT` for a repeat, `409 SOURCE_REMOVED` otherwise). Paragraphs are
numbered B1..Bn in that order and labelled by kind; several versions of one kind are numbered in
pinned order ("transcript 2 paragraph 3"). `runs_pinning_sources` in `client.py` tells `sources`
which runs pinned a version, so a source in use cannot be removed (ADR 0009).

When a draft is ready, the same transaction that marks the run `ready_for_review` saves its
candidate through `backlog.client` and hands its people to `projects.client`; a candidate the
backlog module refuses fails the run with `CANDIDATE_REFUSED` and saves neither. `candidate.py`
applies what a prompt cannot guarantee: an unresolvable citation is dropped (so the claim becomes
proposed), a skipped question stays an open decision even if the draft does not raise it again, a
criterion that quotes a disputed value is withheld and its story blocked, and a story that
implements excluded work is blocked.

## People

A `draft-backlog.v4` draft lists each person the sources name: `ref` (P1...), `name`, `role`,
`said` (one sentence in the model's words), `citations`, `rights` (`decides`, `advises` or
`not_stated`) and `rights_citations`. The model only reports a right a source states; it never
decides who has one, and confirming a right is a person's action in `projects`.

| Check code                      | Fails when                                                    |
| ------------------------------- | ------------------------------------------------------------- |
| `person_without_citation`       | A person has no citation                                      |
| `person_not_named`              | No block the person cites contains their name                 |
| `stated_right_without_citation` | `rights` is `decides` or `advises` with no `rights_citations` |

People citations also go through `unknown_block` and `quote_not_verbatim`, and requests restrict
them to the request's block ids. Any of these triggers the one targeted repair, whose patch may
replace a person by `ref`. What is stored is decided in code (`to_people`), whatever the draft or
its remaining problems say: a person is kept only when a pinned source paragraph they cite
contains their name, a stated right only with a quote that resolves (otherwise `not_stated`),
reviewer answers do not count as sources about people, and names, roles, summaries, quotes and
the number of people are cut to the limits `projects.client` publishes.

The people section's size limits are sent to the provider but not enforced by validation, so an
over-long entry cannot invalidate a whole draft. Its schema is kept small because every draft
request must fit the backup provider's per-request allowance (ADR 0006 notes).

## Conversation

Each project has one append-only conversation (`agent_messages`), read with
`GET /projects/{id}/messages` (newest first, cursor-paged, with each mentioned question's current
state and any work in progress). The decision and its limits are in
[ADR 0010](../../docs/adr/0010-conversation-and-read-only-replies.md); what is where:

- `POST /projects/{id}/messages` stores a message and a run in `reply` mode. The client advances
  and stops it with the run routes. `409 AGENT_BUSY` while a run is created or running, and a run
  cannot start while a reply is; `change_request` needs a baseline and starts a change run (see
  Change runs).
- A reply step (`take_reply_step`) runs the prompt the run pinned. Under `reply-v1` it is one call
  with no tools. Under `reply-v2` each step is one call offering the read-only lookups and the
  `reply` tool (`tool_choice: any`): a lookup is run in code, recorded as a tool step
  (`is_error`, `refused`, `found`) and the run stays `running` for the next advance; `reply` ends
  it. After 3 tool calls, or with one model turn left, only `reply` is offered, so a fourth
  lookup is refused and the run still ends with a reply. An invalid `reply` gets one more turn
  with the problem, then fails the run. Lookup arguments are enums of the labels the model saw
  (B/A blocks, E/S items, D decisions) and are checked again in code.
- `resolve_claims` keeps a citation only when its quote is in the block it names (`B..`
  paragraphs, `A..` recorded answers); a claim left with none is the agent's own. Backlog labels
  in a claim's text become the item's title or the decision's subject. The reply is recorded as
  `generate` steps plus a `validate_reply` tool step with counts (and `lookups` under
  `reply-v2`).
- Under `reply-v3` the `reply` tool may also carry one suggestion: `change_request`
  (`request_text`), `answer_decision` (a `D` label and the answer) or `start_draft`
  ([ADR 0013](../../docs/adr/0013-suggested-actions-in-replies.md)). `check_suggestion` keeps it
  only if the project can take that step now and its values hold (an answer must be copied from
  the reviewer's message); otherwise it is dropped and `validate_reply` records `suggestion`,
  `suggestion_kind` and `suggestion_dropped` as codes. A kept one is stored with the reply in
  `agent_suggestions` with status `offered`, and returned on the message as `suggestion`.
  `PUT /projects/{id}/messages/{message_id}/suggestion` records `accepted` or `dismissed` once,
  with `expected_revision`, for an editor or approver (`409 SUGGESTION_CHANGED`,
  `409 SUGGESTION_ALREADY_DECIDED`); it runs nothing. The next `reply-v3` reply sees earlier
  suggestions and their status as data.
- `GET /runs/{id}` returns a reply run's `lookups` (tool, `found`, `refused`) from its steps, so
  the chat can show what the agent is doing; never what it looked for.
- Runs add their own messages (started, questions, answers, skips, changed answers, ready,
  failed, stopped) in the transaction that stores the action.
- Deciding a change candidate adds `change.approved` or `change.rejected` (kind `event`, role
  `system`, attributed to the approver) in the decision's transaction, through
  `record_change_outcome`. Besides `run_id` (the change run), it carries `change_request_id` and
  `baseline_version`: the new baseline number for an approval, the unchanged one for a
  rejection. Its text is, for example, "CR-1 was approved as baseline v2."; a rejection's
  reason stays on the decision.
- An answered or skipped question can be changed with `expected_revision` while its round is open
  or once the draft is saved (the draft moves to its next revision through `backlog.client`),
  never once that version is approved or rejected.

New reply runs pin `reply-v3` (schema `reply.v3`, `CONVERSATION_REPLY`): `reply-v2`'s lookups,
answered through the `reply` tool, plus one suggestion. Measured against `reply-v1` on
2026-10-17 it held every scored group, cited more and suggested the expected step every time, at
about 60% more estimated cost (see [evals/README.md](../../evals/README.md)). Runs created before
keep the prompt they pinned; `reply-v1` (schema `reply.v1`) and `reply-v2` (schema `reply.v2`)
stay selectable with `just evals-reply --prompt`, as does `reply-v4` (schema `reply.v3`):
`reply-v3` plus confirmed speakers, not measured yet.

## Change runs

A change request is submitted as a `change_request` message or as `POST /projects/{id}/runs`
with `mode: "change"`, `base_version_id`, `base_content_hash` and `request_text` (1 to 2,000
characters). Both need the editor role and an `Idempotency-Key`, and both go through
`submit_change_request`, which in one transaction stores the text as a source version, opens the
change request in `change_control`, creates the run, posts the message and records
`change.requested` ([ADR 0011](../../docs/adr/0011-change-requests-and-stable-id-change-sets.md)).
Refused with `409 BASELINE_REQUIRED` before a baseline exists, `409 BASELINE_CHANGED` when the
id or hash is not the current baseline's (with `details.current_baseline_id`), and
`409 AGENT_BUSY` while another run is working or another change is analysed.

The run pins the baseline's sources plus the request, and its prompt version (`CHANGE_RUN`,
now `change-v1`); each step uses the prompt the run pinned (`change_name`). Its explore step
(`change-explore-v1`) may ask the reviewer; its change step (`change-v1`, schema
`change-set.v1`) sees the baseline
under labels (E1, S1, S1.C1, X1, D1) and returns a change set. The schema limits references to
those labels and the run's block ids. `find_change_problems` then checks it in code:

| Check code                            | Fails when                                                            |
| ------------------------------------- | --------------------------------------------------------------------- |
| `invalid_target`                      | An operation names an item or criterion not in the baseline           |
| `duplicate_target`                    | Two operations touch the same item                                    |
| `incomplete_operation`                | An operation lacks what its kind needs, or changes nothing            |
| `unrelated_operation`                 | An operation cites neither the request nor a reviewer answer          |
| `wholesale_rewrite`                   | More than `max(2, ⌈stories/2⌉)` baseline stories are modified/removed |
| `replaced_not_modified`               | A story is removed and re-added instead of modified                   |
| `reversal_without_decision`           | Excluded or decided work comes back without a scope decision          |
| `outcome_mismatch`                    | `no_change_needed` with operations, or `change` with none             |
| `unknown_block`, `quote_not_verbatim` | A citation names an unknown block or misquotes it                     |

Any problem triggers one repair; a change set that still fails ends the run `failed` with
`CHANGE_REJECTED` (or `INVALID_MODEL_OUTPUT`) and nothing is saved. A sound one is mapped to
stable ids (`to_change_proposal`), with each reversal as an open scope decision that copies the
original evidence from the baseline, and saved through `backlog.client` as a candidate in review
(`backlog` refusing it is `CHANGE_REFUSED`); the run ends `ready_for_review`. `no_change_needed`
saves nothing and ends the run `completed`. In both cases the analysis is recorded on the change
request, the thread gets the agent's cited analysis, and `change.analyzed` is recorded; a failed
or stopped run marks the request `failed`. No step writes the baseline. When an approver
decides the candidate, the thread gets `change.approved` or `change.rejected` (see
Conversation). Tested end to end in
`apps/api/tests/test_change_requests.py` and offline in `tests/test_changing.py`.

Run actions are recorded in the project's activity log through `audit.client`, in the transaction
that stores them: `run.started`, `run.cancelled`, `clarification.answered`,
`clarification.skipped`, `clarification.answer_changed`, `message.sent` and `change.requested`
for the reviewer, `clarification.requested`, `message.replied`, `change.analyzed` and
`run.failed` (with the error code, never its message) for the agent. A replayed
request and a discarded step record nothing, and no event holds a question or an answer.

Tests use the fake provider or a local HTTP server; no test calls a real model. The live probe is
`just probe-model` (in `apps/api`). Run behaviour is tested end to end in
`apps/api/tests/test_runs.py`, from clarification to the saved backlog in
`apps/api/tests/test_backlog_candidates.py`, from a run to the stored people in
`apps/api/tests/test_people.py`, and the conversation in `apps/api/tests/test_conversation.py`.

Tables are prefixed `agent_` (ADR 0003).

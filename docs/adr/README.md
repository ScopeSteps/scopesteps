# Architecture Decision Records

An ADR records one significant decision: the context, the decision and its consequences. ADRs are
immutable once accepted; to change a decision, write a new ADR that supersedes the old one.

Create one by copying [template.md](template.md) to `NNNN-short-title.md` with the next number.

| ADR                                                            | Title                                                           | Status                                         |
| -------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------- |
| [0001](0001-modular-monolith.md)                               | Modular monolith with service-shaped modules                    | Accepted; data decision superseded by 0003     |
| [0002](0002-repository-structure.md)                           | Monorepo structure and naming                                   | Accepted                                       |
| [0003](0003-sqlite-locally-and-table-prefixes.md)              | SQLite locally, Postgres hosted, table prefixes per module      | Accepted                                       |
| [0004](0004-model-provider.md)                                 | Model provider: Gemini 3.5 Flash-Lite behind one adapter        | Accepted                                       |
| [0005](0005-durable-agent-runs.md)                             | Durable agent runs: one leased step per request                 | Accepted                                       |
| [0006](0006-groq-backup-provider.md)                           | Groq as a backup provider, with opt-in fallback at run start    | Accepted                                       |
| [0007](0007-password-sign-in-and-server-side-sessions.md)      | Password sign-in with server-side sessions                      | Accepted                                       |
| [0008](0008-atomic-baseline-approval.md)                       | Atomic baseline approval with append-only decisions             | Accepted                                       |
| [0009](0009-sources-of-any-kind-and-soft-removal.md)           | Sources of any kind, explicit new versions, guarded removal     | Accepted                                       |
| [0010](0010-conversation-and-read-only-replies.md)             | A saved conversation, with one read-only reply run per message  | Accepted                                       |
| [0011](0011-change-requests-and-stable-id-change-sets.md)      | Change requests analysed into a stable-id change set            | Accepted                                       |
| [0012](0012-speaker-identity-confirmed-by-people.md)           | Transcript speakers found by a parser, and confirmed by people  | Accepted; non-blocking part superseded by 0015 |
| [0013](0013-suggested-actions-in-replies.md)                   | A reply may suggest one next step, which a person takes         | Accepted                                       |
| [0014](0014-jira-csv-export.md)                                | Approved backlogs export as a Jira CSV; Markdown is removed     | Accepted                                       |
| [0015](0015-people-before-questions.md)                        | Say who the speakers are before the agent asks its questions    | Accepted                                       |
| [0016](0016-agpl-license.md)                                   | License the code under the GNU AGPL v3                          | Accepted                                       |
| [0017](0017-heldout-packs-in-a-private-repository.md)          | Held-out packs in a private repository; the lock stays public   | Accepted                                       |
| [0018](0018-labelled-replay-of-a-recorded-run.md)              | Labelled replay of a recorded run for e2e tests and demos       | Accepted                                       |
| [0019](0019-accounts-invitations-and-project-roles.md)         | Open sign-up, invitations by link or email, project roles       | Accepted                                       |
| [0020](0020-discussions-as-their-own-module.md)                | Discussions are their own module and never reach the agent      | Accepted                                       |
| [0021](0021-mentions-followers-and-notifications.md)           | Mentions, following, and notifications with batched emails      | Accepted                                       |
| [0022](0022-export-model-call-telemetry-over-otlp.md)          | Model-call telemetry exported over OTLP, local Grafana backend  | Accepted                                       |
| [0023](0023-alert-rules-as-code-from-evaluation-results.md)    | Alert rules as code, thresholds set from evaluation results     | Accepted                                       |
| [0024](0024-one-ordered-role-per-project-member.md)            | One ordered role per project member, checked as permissions     | Accepted                                       |
| [0025](0025-word-pdf-and-webvtt-sources-converted-to-text.md)  | Word, PDF and WebVTT sources, converted to text when uploaded   | Accepted                                       |
| [0026](0026-long-sources-checked-to-fit-before-a-run.md)       | Long sources, sent whole and checked to fit before a run starts | Accepted                                       |
| [0027](0027-openly-licensed-public-datasets-for-evaluation.md) | Openly licensed public datasets in evaluation packs             | Accepted                                       |
| [0028](0028-drafting-in-steps-without-the-size-cap.md)         | Drafting in steps, without the 2-epic, 8-story cap              | Accepted                                       |

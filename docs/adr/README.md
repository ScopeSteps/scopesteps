# Architecture Decision Records

An ADR records one significant decision: the context, the decision and its consequences. ADRs are
immutable once accepted; to change a decision, write a new ADR that supersedes the old one.

Create one by copying [template.md](template.md) to `NNNN-short-title.md` with the next number.

| ADR                                                       | Title                                                          | Status                                         |
| --------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------- |
| [0001](0001-modular-monolith.md)                          | Modular monolith with service-shaped modules                   | Accepted; data decision superseded by 0003     |
| [0002](0002-repository-structure.md)                      | Monorepo structure and naming                                  | Accepted                                       |
| [0003](0003-sqlite-locally-and-table-prefixes.md)         | SQLite locally, Postgres hosted, table prefixes per module     | Accepted                                       |
| [0004](0004-model-provider.md)                            | Model provider: Gemini 3.5 Flash-Lite behind one adapter       | Accepted                                       |
| [0005](0005-durable-agent-runs.md)                        | Durable agent runs: one leased step per request                | Accepted                                       |
| [0006](0006-groq-backup-provider.md)                      | Groq as a backup provider, with opt-in fallback at run start   | Accepted                                       |
| [0007](0007-password-sign-in-and-server-side-sessions.md) | Password sign-in with server-side sessions                     | Accepted                                       |
| [0008](0008-atomic-baseline-approval.md)                  | Atomic baseline approval with append-only decisions            | Accepted                                       |
| [0009](0009-sources-of-any-kind-and-soft-removal.md)      | Sources of any kind, explicit new versions, guarded removal    | Accepted                                       |
| [0010](0010-conversation-and-read-only-replies.md)        | A saved conversation, with one read-only reply run per message | Accepted                                       |
| [0011](0011-change-requests-and-stable-id-change-sets.md) | Change requests analysed into a stable-id change set           | Accepted                                       |
| [0012](0012-speaker-identity-confirmed-by-people.md)      | Transcript speakers found by a parser, and confirmed by people | Accepted; non-blocking part superseded by 0015 |
| [0013](0013-suggested-actions-in-replies.md)              | A reply may suggest one next step, which a person takes        | Accepted                                       |
| [0014](0014-jira-csv-export.md)                           | Approved backlogs export as a Jira CSV; Markdown is removed    | Accepted                                       |
| [0015](0015-people-before-questions.md)                   | Say who the speakers are before the agent asks its questions   | Accepted                                       |
| [0016](0016-agpl-license.md)                              | License the code under the GNU AGPL v3                         | Accepted                                       |

# Architecture Decision Records

An ADR records one significant decision: the context, the decision and its consequences. ADRs are
immutable once accepted; to change a decision, write a new ADR that supersedes the old one.

Create one by copying [template.md](template.md) to `NNNN-short-title.md` with the next number.

| ADR                                                       | Title                                                        | Status                                     |
| --------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------ |
| [0001](0001-modular-monolith.md)                          | Modular monolith with service-shaped modules                 | Accepted; data decision superseded by 0003 |
| [0002](0002-repository-structure.md)                      | Monorepo structure and naming                                | Accepted                                   |
| [0003](0003-sqlite-locally-and-table-prefixes.md)         | SQLite locally, Postgres hosted, table prefixes per module   | Accepted                                   |
| [0004](0004-model-provider.md)                            | Model provider: Gemini 3.5 Flash-Lite behind one adapter     | Accepted                                   |
| [0005](0005-durable-agent-runs.md)                        | Durable agent runs: one leased step per request              | Accepted                                   |
| [0006](0006-groq-backup-provider.md)                      | Groq as a backup provider, with opt-in fallback at run start | Accepted                                   |
| [0007](0007-password-sign-in-and-server-side-sessions.md) | Password sign-in with server-side sessions                   | Accepted                                   |

# Architecture Decision Records

An ADR records one significant decision: the context, the decision and its consequences. ADRs are
immutable once accepted; to change a decision, write a new ADR that supersedes the old one.

Create one by copying [template.md](template.md) to `NNNN-short-title.md` with the next number.

| ADR                                               | Title                                                      | Status                                     |
| ------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------ |
| [0001](0001-modular-monolith.md)                  | Modular monolith with service-shaped modules               | Accepted; data decision superseded by 0003 |
| [0002](0002-repository-structure.md)              | Monorepo structure and naming                              | Accepted                                   |
| [0003](0003-sqlite-locally-and-table-prefixes.md) | SQLite locally, Postgres hosted, table prefixes per module | Accepted                                   |

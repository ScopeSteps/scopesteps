# scopesteps-infrastructure

Technical building blocks shared by module `infrastructure/` and `http/` layers:

- `database`: declarative `Base` with constraint naming conventions, `UtcDateTime`, and an
  engine factory that enables SQLite foreign keys and WAL.
- `http`: FastAPI dependencies `SessionDep` and `IdempotencyKey`.

Domain code never imports this package; import-linter enforces it.

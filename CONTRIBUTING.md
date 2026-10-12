# Contributing

## Workflow

1. Branch from `main`: `<type>/<short-description>`, e.g. `feat/source-upload`.
2. Commit with one-line [Conventional Commits](https://www.conventionalcommits.org/):
   `type(scope): summary`. Scope is the module or app, e.g. `feat(sources): validate upload size`.
   The commit-msg hook checks this.
3. Run `just check` before pushing. CI runs the same checks.
4. Open a pull request using the template. PRs are squash-merged, so the PR title must also be a
   Conventional Commit.

## Architecture rules

These are enforced in CI, not just by review.

- **Modules talk through `client.py` only.** Never import another module's `domain`,
  `application`, `infrastructure` or `http` package.
- **Layers point inward:** `http` / `infrastructure` → `application` → `domain`. `domain` is
  pure Python: no FastAPI, SQLAlchemy or Pydantic.
- **Each module owns its tables** in its own Postgres schema. Reference other modules' data by ID.
- **Apps contain no business logic.** They load settings and wire modules together.
- **The API contract is generated.** After changing an endpoint, run `just contract` and commit
  the result. Breaking changes must be called out in the PR.

## Adding a module

1. Copy the layout of an existing module under `modules/<name>/`.
2. Rename the package (`scopesteps-<name>`) and `module-name` (`scopesteps.<name>`).
3. Register it in `apps/api/src/scopesteps/api/modules.py`, add it to `apps/api` dependencies
   and root `[tool.uv.sources]`, and add its import-linter contracts in the root `pyproject.toml`.
4. Record the decision in an ADR if it introduces a new bounded context.

## Code style

- **Python:** ruff (lint + format), pyright strict, pytest. Type hints on all functions.
- **TypeScript:** strict mode, ESLint + Prettier, Vitest + Testing Library. Function components
  and hooks.
- **Tests:** arrange/act/assert, behaviour-focused names, table-driven where it fits.

## Data and secrets

Use synthetic or de-identified data only. Never commit `.env`, real documents or credentials.

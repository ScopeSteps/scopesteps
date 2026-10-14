# AGENTS.md

ScopeSteps turns meetings and documents into evidence-backed backlogs. It is a Python modular
monolith (FastAPI) with a React + TypeScript web app and an evaluation harness for the AI agent.

Workflow, architecture rules and code style are in [CONTRIBUTING.md](CONTRIBUTING.md); read it
first. This file adds what an agent needs on top.

## Commands

Run from the repo root (see `justfile`; `just` lists everything).

| Command                  | What it does                                                          |
| ------------------------ | --------------------------------------------------------------------- |
| `just setup`             | Install dependencies and git hooks, create `.env`, migrate, seed      |
| `just lint`              | ruff check and format check, ESLint, Prettier                         |
| `just typecheck`         | pyright (strict) and `tsc`                                            |
| `just test`              | pytest and Vitest                                                     |
| `just check`             | Everything CI runs: secrets, lint, types, boundaries, tests, contract |
| `just format`            | Auto-format and auto-fix                                              |
| `just evals-validate`    | Validate evaluation packs and the held-out lock (no model calls)      |
| `just evals-single-pass` | Score the single-pass baseline on the dev packs (live model calls)    |
| `just evals-agent`       | Score full agent runs with a scripted reviewer (live model calls)     |

## Layout

- `apps/api`, `apps/web`: deployables; no business logic.
- `modules/<name>`: one bounded context each; other modules use only its `client.py`.
- `packages/`: shared kernel and the generated TypeScript API client.
- `evals/`: evaluation packs, scoring and runners; results in `evals/README.md`.
- `docs/`: architecture, ADRs, product, roadmap. Start at [docs/README.md](docs/README.md).

## Hard rules

- Synthetic or de-identified data only, in code, tests, fixtures and model calls.
- Never commit secrets, credentials or `.env`. Do not read or print `.env`.
- Never open, quote or tune against `evals/datasets/heldout/`.
- Ask before any live model run (`just probe-model`, `just evals-single-pass`, `just evals-agent`);
  they spend quota.
- Commits are one-line Conventional Commits (`type(scope): summary`). Never force-push.

## Skills

Project skills live in `.claude/skills/`. Read the one that applies before starting.

| Skill              | Use when                                                                |
| ------------------ | ----------------------------------------------------------------------- |
| `python`           | Writing or changing any `.py` file, module, endpoint or migration       |
| `typescript-react` | Writing or changing `.ts`/`.tsx` in `apps/web` or `packages/`           |
| `agent-harness`    | Touching `modules/agent` or `evals/`: prompts, providers, checks        |
| `design-system`    | Building or changing any screen, component, theme or copy in `apps/web` |
| `jira-tickets`     | Writing, linking, ordering or closing SSPOC tickets                     |
| `code-comments`    | Writing, reviewing or cleaning up comments and docstrings               |
| `commit`           | Staging and committing                                                  |
| `pull-request`     | Pushing, opening or reviewing a pull request                            |

## Definition of done

A change is done when all of these hold:

1. `just check` passes (secrets, lint, types, boundaries, tests, migrations, contract).
2. Docs touched by the change are updated in the same pull request:
   - the module's `README.md`;
   - `docs/architecture/` if structure, data flow or boundaries changed;
   - `docs/status/roadmap.md` if a status changed;
   - `evals/README.md` for harness, prompt, check or scoring changes;
   - the relevant skill in `.claude/skills/` if a convention changed;
   - ADRs: a new ADR for a new or reversed decision, or a dated note on the existing one. Never
     change an accepted ADR's decision silently.
3. Comments and docstrings near the changed code are still true (see the `code-comments`
   skill). An ADR is the single source of truth for its decision: point to it, do not copy it.
4. The Jira ticket's acceptance criteria and status are updated.

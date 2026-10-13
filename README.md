# ScopeSteps

Agentic product scoping: turn meetings and documents into evidence-backed backlogs, with
human-approved baselines and controlled scope changes.

> **Status:** P0 proof of concept in progress. Foundation, source upload, the model provider
> (Gemini, [ADR 0004](docs/adr/0004-model-provider.md)) and the evaluation harness are done; the
> agent run API ([ADR 0005](docs/adr/0005-durable-agent-runs.md)) is in review. See [docs/status/roadmap.md](docs/status/roadmap.md).

## Repository layout

```text
apps/                 Deployables
  api/                FastAPI app: mounts the enabled modules
  web/                React + TypeScript single-page app
modules/              Bounded contexts (Python packages, one per business capability)
packages/
  kernel/             Shared kernel: IDs, errors, domain events
  api-client/         TypeScript types generated from the OpenAPI contract
contracts/            Committed OpenAPI contract between api and web
evals/                Annotated evaluation packs, scoring and the single-pass baseline runner
scripts/              Developer scripts
samples/              Synthetic files for trying features by hand
docs/                 Architecture, ADRs, product docs, roadmap and proposals
```

Why it is shaped this way: [ADR 0001](docs/adr/0001-modular-monolith.md) and
[ADR 0002](docs/adr/0002-repository-structure.md).

## Local development

### Prerequisites

| Tool    | Version                            | Install (macOS)                                                      |
| ------- | ---------------------------------- | -------------------------------------------------------------------- |
| uv      | latest                             | `brew install uv`                                                    |
| Node.js | 24 LTS (pinned in `.node-version`) | [fnm](https://github.com/Schniz/fnm), then `fnm install` in the repo |
| pnpm    | pinned in `package.json`           | `corepack enable pnpm` (Corepack ships with Node 24)                 |
| just    | latest                             | `brew install just` or `uv tool install rust-just`                   |

Python does not need a separate install: uv downloads the version pinned in `.python-version`.
fnm is recommended over `brew install node@24` because it installs prebuilt Node binaries
(Homebrew compiles from source on Intel Macs) and switches versions automatically per repo.

### First-time setup

```sh
git clone git@github.com:ScopeSteps/scopesteps.git
cd scopesteps
just setup    # installs dependencies and git hooks, creates .env, migrates and seeds SQLite
```

### Run the app

In two terminals:

```sh
just api      # http://127.0.0.1:8000 (API docs at /docs)
just web      # http://localhost:5173
```

The web app proxies `/api` and `/health` to the API, so no CORS setup is needed locally. The
home page shows "API ready" once the API is up and the database is migrated.

Locally, every request acts as the seeded **Local Reviewer** (Editor + Approver on the demo
project "Campus Room Booking"); check with `curl http://127.0.0.1:8000/api/v1/me`. This mode is
refused unless `APP_ENV` is `local`/`test` and the API listens on loopback, so it cannot be
deployed.

### Everyday commands

| Command                  | What it does                                                                    |
| ------------------------ | ------------------------------------------------------------------------------- |
| `just`                   | List all commands                                                               |
| `just check`             | Run everything CI runs: lint, type-check, boundaries, tests, contract           |
| `just test`              | Python and frontend tests                                                       |
| `just format`            | Auto-format and auto-fix Python and TypeScript                                  |
| `just boundaries`        | Verify module boundaries (import-linter)                                        |
| `just contract`          | Regenerate `contracts/openapi.json` and the TypeScript client after API changes |
| `just migrate`           | Apply database migrations                                                       |
| `just seed`              | Create the local reviewer and demo project (safe to re-run)                     |
| `just reset-db`          | Drop, re-migrate and re-seed the local database                                 |
| `just migration "…"`     | Generate a migration from model changes                                         |
| `just probe-model`       | Live check that the configured model returns typed output and tool calls        |
| `just evals-validate`    | Validate every evaluation pack and the held-out lock                            |
| `just evals-single-pass` | Run and score the single-pass baseline on the dev packs (live model calls)      |

### Configuration

All settings come from environment variables; `.env.example` documents each one. Secrets
(database, model provider keys) stay server-side and are never prefixed with `VITE_`.

### Model provider

The app runs without a model (`MODEL_PROVIDER=none`). Two providers can be configured side by
side; `MODEL_PROVIDER` picks the one in use, and switching is a manual edit, never automatic.

| Provider | Role    | Key                                                                 | Settings                            |
| -------- | ------- | ------------------------------------------------------------------- | ----------------------------------- |
| `gemini` | Primary | Google AI Studio, on a project with **no billing account attached** | `GEMINI_API_KEY`, `GEMINI_MODEL_ID` |
| `groq`   | Backup  | [console.groq.com/keys](https://console.groq.com/keys) (free plan)  | `GROQ_API_KEY`, `GROQ_MODEL_ID`     |

After setting a key, run `just probe-model` to check the selected provider. Free tiers may use or
retain prompts, so send synthetic data only. A run keeps the model it started with; scores from
different models are not comparable. Decisions: [ADR 0004](docs/adr/0004-model-provider.md)
(Gemini, no silent fallback) and [ADR 0006](docs/adr/0006-groq-backup-provider.md) (Groq backup);
evaluation results are in [evals/README.md](evals/README.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

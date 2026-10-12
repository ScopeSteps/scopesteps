# ScopeSteps

Agentic product scoping: turn meetings and documents into evidence-backed backlogs, with
human-approved baselines and controlled scope changes.

> **Status:** walking skeleton. The repository structure, tooling and CI are in place; product
> features are built next, starting with the P0 proof of concept. See
> [docs/status/roadmap.md](docs/status/roadmap.md).

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
scripts/              Developer scripts
docs/                 Architecture, ADRs, product docs, roadmap and proposals
```

Why it is shaped this way: [ADR 0001](docs/adr/0001-modular-monolith.md) and
[ADR 0002](docs/adr/0002-repository-structure.md).

## Local development

### Prerequisites

| Tool    | Version                            | Install (macOS)                                                        |
| ------- | ---------------------------------- | ---------------------------------------------------------------------- |
| uv      | latest                             | `brew install uv`                                                      |
| Node.js | 24 LTS (pinned in `.node-version`) | [fnm](https://github.com/Schniz/fnm), then `fnm install` in the repo   |
| pnpm    | pinned in `package.json`           | `corepack enable pnpm` (Corepack ships with Node 24)                   |
| just    | latest                             | `brew install just` or `uv tool install rust-just`                     |
| Docker  | Docker Desktop or OrbStack         | `brew install --cask docker-desktop` or `brew install --cask orbstack` |

Python does not need a separate install: uv downloads the version pinned in `.python-version`.
fnm is recommended over `brew install node@24` because it installs prebuilt Node binaries
(Homebrew compiles from source on Intel Macs) and switches versions automatically per repo.

### First-time setup

```sh
git clone git@github.com:ScopeSteps/scopesteps.git
cd scopesteps
just setup    # installs Python + Node dependencies and git hooks, creates .env
just db       # starts Postgres in Docker
```

### Run the app

In two terminals:

```sh
just api      # http://127.0.0.1:8000 (API docs at /docs)
just web      # http://localhost:5173
```

The web app proxies `/api` and `/health` to the API, so no CORS setup is needed locally. The
home page shows "API ready" once both are running and Postgres is up.

### Everyday commands

| Command           | What it does                                                                    |
| ----------------- | ------------------------------------------------------------------------------- |
| `just`            | List all commands                                                               |
| `just check`      | Run everything CI runs: lint, type-check, boundaries, tests, contract           |
| `just test`       | Python and frontend tests                                                       |
| `just format`     | Auto-format and auto-fix Python and TypeScript                                  |
| `just boundaries` | Verify module boundaries (import-linter)                                        |
| `just contract`   | Regenerate `contracts/openapi.json` and the TypeScript client after API changes |
| `just down`       | Stop Postgres                                                                   |

### Configuration

All settings come from environment variables; `.env.example` documents each one. Secrets
(database, model provider keys) stay server-side and are never prefixed with `VITE_`.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

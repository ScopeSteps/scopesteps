# ScopeSteps

Agentic product scoping: turn meetings and documents into evidence-backed backlogs, with
human-approved baselines and controlled scope changes.

> **Status:** P0 proof of concept complete, scope frozen 2026-10-20: sources, who's who, the
> agent's clarifying questions, an evidence-backed draft, approval of baseline v1, a change request
> analysed into a stable-id diff and approved or rejected, and the Jira CSV export. Evaluated on
> held-out packs against a single-pass baseline: [POC evaluation](docs/status/poc-evaluation.md).
> The demonstration script is in [docs/demo](docs/demo/README.md); what comes next is in
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
evals/                Annotated evaluation packs, scoring and the single-pass baseline runner
scripts/              Developer scripts
samples/              Synthetic files for trying features by hand
docs/                 Architecture, ADRs, product docs, the UI prototype, roadmap and proposals
```

Why it is shaped this way: [ADR 0001](docs/adr/0001-modular-monolith.md) and
[ADR 0002](docs/adr/0002-repository-structure.md).

## Local development

### Prerequisites

| Tool     | Version                            | Install (macOS)                                                      |
| -------- | ---------------------------------- | -------------------------------------------------------------------- |
| uv       | latest                             | `brew install uv`                                                    |
| Node.js  | 24 LTS (pinned in `.node-version`) | [fnm](https://github.com/Schniz/fnm), then `fnm install` in the repo |
| pnpm     | pinned in `package.json`           | `corepack enable pnpm` (Corepack ships with Node 24)                 |
| just     | latest                             | `brew install just` or `uv tool install rust-just`                   |
| gitleaks | latest                             | `brew install gitleaks` (the pre-commit hook scans staged changes)   |

Python does not need a separate install: uv downloads the version pinned in `.python-version`.
fnm is recommended over `brew install node@24` because it installs prebuilt Node binaries
(Homebrew compiles from source on Intel Macs) and switches versions automatically per repo.

### First-time setup

```sh
git clone git@github.com:ScopeSteps/scopesteps.git
cd scopesteps
just setup    # installs dependencies and git hooks, creates .env with a sign-in password, migrates and seeds SQLite
```

No secrets are needed: `.env` is made from `.env.example`, its sign-in password is generated
locally, and the app runs without a model (`MODEL_PROVIDER=none`) until you add a key. Verified
from a clean clone on 2026-10-21 with the commands above, then `just test` and `just e2e`.

For the browser test, install Chromium once:
`pnpm --filter @scopesteps/e2e exec playwright install chromium`.

### Run the app

In two terminals:

```sh
just api      # http://127.0.0.1:8000 (API docs at /docs)
just web      # http://localhost:5173
```

The web app proxies `/api` and `/health` to the API, so no CORS setup is needed locally. The
home page shows "API ready" once the API is up and the database is migrated.

Sign in at http://localhost:5173 as `viewer@scopesteps.local`, `editor@scopesteps.local` or
`approver@scopesteps.local`, one synthetic account per role on the demo project "Campus Room
Booking". They share the password in `SEED_ACCOUNT_PASSWORD` in your `.env`, which `just setup`
generates; set your own (12+ characters) and run `just seed` to change it. Sessions are
server-side, in an HttpOnly cookie
([ADR 0007](docs/adr/0007-password-sign-in-and-server-side-sessions.md)).

An `.env` made before sign-in existed says `AUTH_MODE=local`: every request then acts as the
seeded **Local Reviewer** and sign-in is disabled. Delete that line, run `just setup` to get a
password, and restart the API. `AUTH_MODE=local` stays available for scripted local work and is
refused unless `APP_ENV` is `local`/`test` and the API listens on loopback, so it cannot be
deployed. See [modules/identity/README.md](modules/identity/README.md).

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
| `just seed`              | Create the demo project, local reviewer and role accounts (safe to re-run)      |
| `just reset-db`          | Drop, re-migrate and re-seed the local database                                 |
| `just migration "…"`     | Generate a migration from model changes                                         |
| `just probe-model`       | Live check that the configured model returns typed output and tool calls        |
| `just e2e`               | The critical flow in a browser, on a recorded replay ([e2e/](e2e/README.md))    |
| `just evals-validate`    | Validate every evaluation pack and the held-out lock (when cloned)              |
| `just evals-single-pass` | Run and score the single-pass baseline on the dev packs (live model calls)      |

### Configuration

All settings come from environment variables; `.env.example` documents each one. Secrets
(database, model provider keys) stay server-side and are never prefixed with `VITE_`.

### Model provider

The app runs without a model (`MODEL_PROVIDER=none`). Two providers can be configured side by
side; `MODEL_PROVIDER` is the primary.

| Provider | Role    | Key                                                                 | Settings                            |
| -------- | ------- | ------------------------------------------------------------------- | ----------------------------------- |
| `gemini` | Primary | Google AI Studio, on a project with **no billing account attached** | `GEMINI_API_KEY`, `GEMINI_MODEL_ID` |
| `groq`   | Backup  | [console.groq.com/keys](https://console.groq.com/keys) (free plan)  | `GROQ_API_KEY`, `GROQ_MODEL_ID`     |

`MODEL_FALLBACK_PROVIDER=groq` lets a run that has not had a successful call move to the backup
when the primary is overloaded, and starts new runs there while it keeps failing. A run never
switches model midway, and probes and evaluations never fall back. Check a provider with
`just probe-model --provider groq`. Free tiers may use or retain prompts, so send synthetic data
only. Decisions: [ADR 0004](docs/adr/0004-model-provider.md) (Gemini) and
[ADR 0006](docs/adr/0006-groq-backup-provider.md) (backup and fallback); evaluation results are in
[evals/README.md](evals/README.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Report security problems privately as described in [SECURITY.md](SECURITY.md). Everyone taking
part follows the [code of conduct](CODE_OF_CONDUCT.md).

## License

ScopeSteps is licensed under the [GNU Affero General Public License v3.0](LICENSE). If you run a
modified version as a service, you must offer its users the modified source. See
[ADR 0016](docs/adr/0016-agpl-license.md).

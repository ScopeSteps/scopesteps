# List available recipes.
default:
    @just --list

# Install all dependencies and git hooks.
setup:
    uv sync --all-packages
    pnpm install
    pnpm exec lefthook install
    @test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
    just migrate seed

# Apply database migrations.
migrate:
    uv run alembic -c apps/api/alembic.ini upgrade head

# Create the demo project, the local reviewer and one account per role (safe to re-run).
seed:
    uv run scopesteps-seed

# Drop all tables, re-migrate and re-seed the local database.
reset-db:
    uv run alembic -c apps/api/alembic.ini downgrade base
    just migrate seed

# Generate a migration from model changes: just migration "add sources tables"
migration message:
    uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "{{message}}"

# Optional: start Postgres instead of SQLite (see DATABASE_URL in .env.example).
db:
    docker compose up --detach --wait

# Stop local services.
down:
    docker compose down

# Run the API with reload on http://127.0.0.1:8000.
api:
    uv run scopesteps-api

# Run the frontend on http://localhost:5173.
web:
    pnpm --filter @scopesteps/web dev

# Run every check CI runs.
check: secrets lint ticket-ids typecheck boundaries test migrations-check contract-check

# Jira keys belong in branches, commits and pull requests, never in code (code-comments skill).
ticket-ids:
    ! git grep -nE 'SSPOC-[0-9]+' -- '*.py' '*.ts' '*.tsx' '*.js' '*.css'

# Scan every commit for secrets (CI runs the same scan).
secrets:
    gitleaks git --redact --no-banner .

# Lint and format-check Python and TypeScript.
lint:
    uv run ruff check .
    uv run ruff format --check .
    pnpm --filter @scopesteps/web lint
    pnpm exec prettier --check .

# Format all code.
format:
    uv run ruff check --fix .
    uv run ruff format .
    pnpm exec prettier --write .

# Type-check Python (strict) and TypeScript.
typecheck:
    uv run pyright
    pnpm --filter @scopesteps/web typecheck

# Enforce module boundaries.
boundaries:
    uv run lint-imports

# Run all unit and integration tests.
test:
    uv run pytest
    pnpm --filter @scopesteps/web test

# Fail if models and migrations have drifted (uses a throwaway database).
migrations-check:
    DATABASE_URL=sqlite:///var/migrations-check.db uv run alembic -c apps/api/alembic.ini upgrade head
    DATABASE_URL=sqlite:///var/migrations-check.db uv run alembic -c apps/api/alembic.ini check

# Regenerate the OpenAPI contract and the TypeScript client.
contract:
    uv run python scripts/export_openapi.py
    pnpm --filter @scopesteps/api-client generate
    pnpm exec prettier --write contracts packages/api-client/src

# Fail if the committed contract or client is out of date.
contract-check: contract
    git diff --exit-code -- contracts packages/api-client/src

# Validate every evaluation pack and the held-out lock.
evals-validate:
    uv run scopesteps-evals validate

# Run and score the single-pass baseline (live model calls; dev packs unless --split heldout --final).
evals-single-pass *args:
    uv run scopesteps-evals single-pass {{args}}

# Run and score full agent runs with a scripted reviewer (live model calls; dev packs by default).
evals-agent *args:
    uv run scopesteps-evals agent {{args}}

# Run and score agent replies to the dev packs' reply questions (live model calls).
evals-reply *args:
    uv run scopesteps-evals reply {{args}}

# Lock the held-out packs with a checksum manifest (run once, then commit).
evals-freeze:
    uv run scopesteps-evals freeze-heldout

# Probe the configured model live (uses real quota; synthetic data only).
probe-model *args:
    uv run scopesteps-probe-model {{args}}

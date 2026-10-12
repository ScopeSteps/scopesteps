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

# Create the local reviewer and demo project (safe to re-run).
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
check: lint typecheck boundaries test migrations-check contract-check

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

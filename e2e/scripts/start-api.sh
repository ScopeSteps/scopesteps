#!/usr/bin/env bash
# Start a fresh API for the end-to-end tests: an empty database of its own, migrated and seeded,
# on its own port, so a developer's `just api` and local data are left alone.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p var
uv run python -m scopesteps.api.reset_db
uv run alembic -c apps/api/alembic.ini upgrade head
uv run scopesteps-seed
exec uv run scopesteps-api

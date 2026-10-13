# scopesteps-api

The HTTP API deployable. It contains no business logic: it loads settings, mounts the routers
of the modules listed in `ENABLED_MODULES`, and exposes health checks.

```sh
just api          # from the repo root: run with reload on http://127.0.0.1:8000
```

- `GET /health/live` — the process is up.
- `GET /health/ready` — the database is reachable and fully migrated. Never calls a model
  provider.

Also owns the composition root (`main.py`), the error envelope, request IDs, the cross-site
request guard (`cross_site.py`, ADR 0007), the Alembic migrations (`migrations/`, config in
`alembic.ini`) and the local seed (`just seed`).

- OpenAPI docs at `/docs` outside production.

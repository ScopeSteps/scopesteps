# scopesteps-api

The HTTP API deployable. It contains no business logic: it loads settings, mounts the routers
of the modules listed in `ENABLED_MODULES`, and exposes health checks.

```sh
just api          # from the repo root: run with reload on http://127.0.0.1:8000
```

- `GET /health/live` — the process is up.
- `GET /health/ready` — the database is reachable. Never calls a model provider.
- OpenAPI docs at `/docs` outside production.

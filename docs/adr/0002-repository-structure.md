# 0002. Monorepo structure and naming

- Status: Accepted
- Date: 2026-10-11

## Context

The frontend, API and agent share one contract and most features touch all of them. Separate
repositories would mean coordinated multi-repo pull requests and contract drift.

## Decision

One repository, `ScopeSteps/scopesteps`, using the common `apps/` + `packages/` monorepo
convention:

- `apps/` contains only deployables, named after what they deploy: `web`, `api`, later `worker`.
- `modules/` contains bounded contexts as Python packages. The name avoids `services/`, which
  usually implies separately deployed microservices.
- `packages/` contains shared libraries: `kernel` (Python) and `api-client` (TypeScript).
- Python packages are distributed as `scopesteps-<name>` and imported as `scopesteps.<name>`
  (PEP 420 namespace packages, src layout).
- TypeScript packages are scoped `@scopesteps/<name>`.
- Reserved modules for later phases (`jira_integration`, `planning`) exist as a README only, and
  are excluded from the uv workspace until built.

Tooling: uv workspace for Python, pnpm workspace for TypeScript, `just` as the single task runner.
No Nx, Turborepo or Bazel until build times justify them.

## Consequences

- One pull request can change the API, the contract and the UI together.
- Every module has a predictable location and name.
- Path-filtered CI keeps feedback fast as the repository grows.

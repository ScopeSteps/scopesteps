# Roadmap and status

Last updated: 2026-10-13. Jira epic: SSPOC-1.

| Phase                     | Scope                                                                                                                                     | Status          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Foundation                | Monorepo, module skeleton, tooling, CI, docs                                                                                              | Done            |
| P0: POC                   | Two text sources → clarification → cited backlog → approved baseline → one change diff → export; evaluated against a single-pass baseline | **In progress** |
| P1: Core platform         | Hosted auth and roles, durable worker, source audit hub, versioned backlog UI, one-way Jira publishing                                    | Planned         |
| P2: Expanded intelligence | PDF/wiki/repository ingestion, evaluated retrieval, stakeholder profiles, planning scenarios                                              | Planned         |
| P3: Hardening             | Two-way Jira sync, operational recovery, security/privacy review, calibrated estimates                                                    | Planned         |

## P0 checklist

- [x] Day 1 (SSPOC-2): React/FastAPI/database scaffold, migrations and seed, local reviewer,
      configuration validation, API contracts for all flows
- [x] Day 1 (SSPOC-3): evaluation pack format, validation and held-out lock; two annotated dev
      packs; two held-out packs written and frozen
- [x] Day 1 (SSPOC-3): Gemini provider adapter, live probe and model decision
      ([ADR 0004](../adr/0004-model-provider.md))
- [x] Day 1 (SSPOC-3): scored single-pass comparison runner (initial inputs; with final
      clarification answers)
- [x] SSPOC-3 follow-up: prompt v2, deterministic draft checks, targeted repair, content-free
      tracing, cost estimates, confidence intervals and recorded regression drafts

Acceptance criteria from the [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md).

- [x] Upload two sources; stable source and block IDs (SSPOC-4)
- [ ] Agent run with clarification (answer and skip) (SSPOC-7, SSPOC-8): run API, leased steps,
      tools, limits and step records in review (PR #16); UI in SSPOC-10
- [ ] Evidence-backed draft backlog with source drawer (SSPOC-8)
- [ ] Draft edits, review and approval into immutable baseline v1 (SSPOC-11)
- [ ] Change request producing a stable-ID diff; approve → v2, reject → v1 unchanged (SSPOC-14, SSPOC-17)
- [ ] Approved-only JSON/Markdown export (SSPOC-20)
- [ ] Evaluation against a single-pass baseline on held-out packs (SSPOC-23)
- [ ] End-to-end Playwright test of the full flow (SSPOC-24)

Update this page in the same pull request that changes a status.

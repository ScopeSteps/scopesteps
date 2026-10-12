# Roadmap and status

Last updated: 2026-10-11.

| Phase                     | Scope                                                                                                                                     | Status          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Foundation                | Monorepo, module skeleton, tooling, CI, docs                                                                                              | **In progress** |
| P0: POC                   | Two text sources → clarification → cited backlog → approved baseline → one change diff → export; evaluated against a single-pass baseline | Next            |
| P1: Core platform         | Hosted auth and roles, durable worker, source audit hub, versioned backlog UI, one-way Jira publishing                                    | Planned         |
| P2: Expanded intelligence | PDF/wiki/repository ingestion, evaluated retrieval, stakeholder profiles, planning scenarios                                              | Planned         |
| P3: Hardening             | Two-way Jira sync, operational recovery, security/privacy review, calibrated estimates                                                    | Planned         |

## P0 checklist

Acceptance criteria from the [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md).

- [ ] Upload two sources; stable source and block IDs
- [ ] Agent run with clarification (answer and skip)
- [ ] Evidence-backed draft backlog with source drawer
- [ ] Draft edits, review and approval into immutable baseline v1
- [ ] Change request producing a stable-ID diff; approve → v2, reject → v1 unchanged
- [ ] Approved-only JSON/Markdown export
- [ ] Evaluation against a single-pass baseline on held-out packs
- [ ] End-to-end Playwright test of the full flow

Update this page in the same pull request that changes a status.

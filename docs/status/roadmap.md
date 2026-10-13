# Roadmap and status

Last updated: 2026-10-13. Jira epic: SSPOC-1.

| Phase                     | Scope                                                                                                                                                                   | Status          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Foundation                | Monorepo, module skeleton, tooling, CI, docs                                                                                                                            | Done            |
| P0: POC                   | Text sources → clarification → cited backlog → approved baseline → one change diff → export; evaluated against a single-pass baseline; product UI from the v1 prototype | **In progress** |
| P1: Core platform         | Hosted deployment and single sign-on, durable worker, source audit hub, one-way Jira publishing                                                                         | Planned         |
| P2: Expanded intelligence | PDF/wiki/repository ingestion, evaluated retrieval, richer stakeholder profiles, planning scenarios                                                                     | Planned         |
| P3: Hardening             | Two-way Jira sync, operational recovery, security/privacy review, calibrated estimates                                                                                  | Planned         |

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
- [x] SSPOC-3 follow-up: prompt v3 with traceable drafts, patch repairs and citations restricted
      to the request's blocks
- [ ] SSPOC-25: re-measure v3 on Gemini once its free tier stops returning 503s
- [x] SSPOC-7: durable agent runs (leased steps, tools, clarification pause and resume, limits,
      step records; [ADR 0005](../adr/0005-durable-agent-runs.md))
- [x] Groq backup provider with opt-in fallback at run start
      ([ADR 0006](../adr/0006-groq-backup-provider.md)); enabled in development, off by default
- [ ] SSPOC-25: confirm the Groq fallback with a 10-draft run after the token-fit fixes (output
      budgets sized to the per-request limit, regenerate on cut-off output, id enums)
- [x] SSPOC-8 (SSPOC-9, SSPOC-10): runs save a validated draft backlog version with claim
      origins, evidence, decisions and blockers; Backlog view with run progress, clarification,
      and the evidence drawer. Prompt `draft-v4` is not yet measured on a live model
- [ ] SSPOC-25: measure `draft-v4` on the dev packs once Gemini's free tier recovers
- [x] CI: secret scanning, job timeouts, PR title check; squash-only merges

## P0 product UI

Decided 2026-10-13: the POC includes the product UI from the v1 prototype
(`ui-prototypes/ScopeSteps-v1.html`, attached to SSPOC-1), built against the live API with none
of its demo features. Each story has a backend and a frontend subtask; the agreed order is in the
comment on SSPOC-1.

- [ ] Design system and app shell (SSPOC-26)
- [ ] Chat, Backlog, Sources and the evidence sheet moved into the new shell (SSPOC-51)
- [ ] Sign-in and sign-out with server-side sessions (SSPOC-27)
- [ ] Create, switch and rename projects (SSPOC-30)
- [ ] Add and remove individual sources (SSPOC-33)
- [ ] Saved conversation with read-only, cited agent replies (SSPOC-36)
- [ ] Version history and compare (SSPOC-39)
- [ ] People named in sources, with corrections and confirmed decision rights (SSPOC-42)
- [ ] Activity log from append-only audit events (SSPOC-45)
- [ ] Profile name, job title and about text; initials, no photo (SSPOC-48)

Approval, change review and export (SSPOC-11 to SSPOC-22) follow the prototype's screens: the
approve modal with server checks, change requests from the chat with a scope decision, the Change
requests page and the export modal.

## P0 acceptance

Acceptance criteria from the [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md).

- [x] Upload two sources; stable source and block IDs (SSPOC-4)
- [x] Agent run with clarification (answer and skip) (SSPOC-7, SSPOC-8)
- [x] Evidence-backed draft backlog with source drawer (SSPOC-8)
- [ ] Draft edits, review and approval into immutable baseline v1 (SSPOC-11)
- [ ] Change request producing a stable-ID diff; approve → v2, reject → v1 unchanged (SSPOC-14, SSPOC-17)
- [ ] Approved-only JSON/Markdown export (SSPOC-20)
- [ ] Evaluation against a single-pass baseline on held-out packs (SSPOC-23)
- [ ] End-to-end Playwright test of the full flow (SSPOC-24)

Update this page in the same pull request that changes a status.

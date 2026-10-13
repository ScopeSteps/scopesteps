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
- [x] SSPOC-25: re-measure v3 on Gemini (2026-10-13: same quality, faster)
- [x] SSPOC-7: durable agent runs (leased steps, tools, clarification pause and resume, limits,
      step records; [ADR 0005](../adr/0005-durable-agent-runs.md))
- [x] Groq backup provider with opt-in fallback at run start
      ([ADR 0006](../adr/0006-groq-backup-provider.md)); enabled in development, off by default
- [ ] SSPOC-25: confirm the Groq fallback with a 10-draft run after the token-fit fixes (output
      budgets sized to the per-request limit, regenerate on cut-off output, id enums); the last
      open item on SSPOC-25, which closes after it
- [x] SSPOC-8 (SSPOC-9, SSPOC-10): runs save a validated draft backlog version with claim
      origins, evidence, decisions and blockers; Backlog view with run progress, clarification,
      and the evidence drawer
- [x] SSPOC-25: measure `draft-v4` on the dev packs (2026-10-13: matches v3 within intervals)
- [x] SSPOC-46: append-only audit events recorded in the action's transaction, and the project
      activity feed; sources, runs, clarification and draft saves emit today (the backend half
      of SSPOC-45)
- [x] CI: secret scanning, job timeouts, PR title check; squash-only merges

## P0 product UI

Decided 2026-10-13: the POC includes the product UI from the v1 prototype
(`ui-prototypes/ScopeSteps-v1.html`, attached to SSPOC-1), built against the live API with none
of its demo features. Each story has a backend and a frontend subtask; the order is under
[P0 build order](#p0-build-order).

- [ ] Design system and app shell (SSPOC-26)
- [ ] Chat, Backlog, Sources and the evidence sheet moved into the new shell (SSPOC-51)
- [ ] Sign-in and sign-out with server-side sessions (SSPOC-27)
- [ ] Create, switch and rename projects (SSPOC-30)
  - [x] Backend (SSPOC-31): project list with roles and scope status, create, revision-checked
        rename, and project detail with the configured limits
  - [ ] Frontend (SSPOC-32): project switcher, New project flow and Project settings
- [ ] Add and remove individual sources (SSPOC-33)
- [ ] Saved conversation with read-only, cited agent replies (SSPOC-36)
- [ ] Version history and compare (SSPOC-39)
- [ ] People named in sources, with corrections and confirmed decision rights (SSPOC-42)
- [ ] Activity log from append-only audit events (SSPOC-45): backend done (SSPOC-46), the
      Activity page is SSPOC-47
- [ ] Profile name, job title and about text; initials, no photo (SSPOC-48)

Approval, change review and export (SSPOC-11 to SSPOC-22) follow the prototype's screens: the
approve modal with server checks, change requests from the chat with a scope decision, the Change
requests page and the export modal.

## P0 build order

Mirrors the [build-order comment on SSPOC-1](https://scopesteps.atlassian.net/browse/SSPOC-1?focusedCommentId=10052)
and the "blocks" links in Jira; change both together. One row per story or task. Rows with the
same stage can run in parallel. A row moves on once everything in "Waits on" is done, and a
backend subtask with no blockers can start before its stage.

| Stage | Ticket          | Delivers                                          | BE · FE | Waits on                       | Unblocks         |
| ----- | --------------- | ------------------------------------------------- | ------- | ------------------------------ | ---------------- |
| 1     | SSPOC-26 (task) | Design system and app shell                       | FE only | Nothing                        | Every FE ticket  |
| 2     | SSPOC-51        | Today's screens in the new shell                  | FE only | 26                             | FE of 33, 36, 11 |
| 2     | SSPOC-27        | Sign in and out (needs an ADR)                    | 28 · 29 | BE: nothing; FE: 28, 26        | 48               |
| 2     | SSPOC-30        | Create, switch and rename projects                | 31 · 32 | BE: nothing; FE: 31, 26        | —                |
| 2     | SSPOC-45        | Activity log from audit events                    | 46 · 47 | BE: nothing; FE: 46, 26        | 11, 17           |
| 2     | SSPOC-42        | People and decision rights (prompt change)        | 43 · 44 | BE: nothing; FE: 43, 26        | 23               |
| 3     | SSPOC-48        | Profile                                           | 49 · 50 | BE: 28; FE: 49, 26             | —                |
| 3     | SSPOC-33        | Add and remove single sources (may change prompt) | 34 · 35 | BE: nothing; FE: 34, 26, 51    | 36               |
| 3     | SSPOC-11        | Edit and approve baseline v1 (the main gate)      | 12 · 13 | BE: 46; FE: 12, 26, 51         | 39, 20, 14, 17   |
| 4     | SSPOC-36        | Saved conversation, cited replies (needs an ADR)  | 37 · 38 | BE: 34; FE: 37, 26, 51         | 14, 23           |
| 4     | SSPOC-39        | Version history and compare                       | 40 · 41 | BE: 12; FE: 40, 13             | —                |
| 4     | SSPOC-20        | JSON and Markdown export                          | 21 · 22 | BE: 12; FE: 13                 | 23               |
| 5     | SSPOC-14        | Change request and stable-ID diff                 | 15 · 16 | BE: 12; FE: 15, 13, 38         | 17               |
| 6     | SSPOC-17        | Approve a change as v2 or reject it               | 18 · 19 | BE: 15, 12, 46; FE: 18, 16, 13 | 23               |
| 7     | SSPOC-23 (task) | Held-out evaluation, safety and recovery tests    | —       | 17, 20, 36, 43                 | 24               |
| 8     | SSPOC-24 (task) | Setup, end-to-end test and demo                   | —       | 23 and every UI story          | —                |

- Ready now: SSPOC-26 (frontend); SSPOC-12, SSPOC-28, SSPOC-34 and SSPOC-43 (backend); the
  SSPOC-25 Groq check. SSPOC-46 and SSPOC-31 are done; SSPOC-47 and SSPOC-32 wait only on
  SSPOC-26.
- Bottlenecks: SSPOC-26 blocks every frontend ticket. SSPOC-12 blocks SSPOC-13, 15, 18, 21 and
  40; SSPOC-46, which it waited on, is done. SSPOC-13 blocks SSPOC-16, 19, 22 and 41.
- Longest chain: SSPOC-26 → 51 → 33 → 36 → 14 → 17 → 23 → 24.
- SSPOC-34, SSPOC-37, SSPOC-43 and SSPOC-15 change the agent. Merge them one at a time and
  measure live only after asking. SSPOC-23 runs on the final prompt.

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

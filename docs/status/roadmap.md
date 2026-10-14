# Roadmap and status

Last updated: 2026-10-14. Jira epic: SSPOC-1.

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
- [x] SSPOC-23 groundwork: a harder third dev pack (`youth-football-registration`), and the
      `draft-v5` experiment recorded but not adopted; v4 stays the prompt (PR #26)
- [x] SSPOC-23 groundwork: `just evals-agent` scores full agent runs with a scripted reviewer
      (PR #27)
- [x] SSPOC-46: append-only audit events recorded in the action's transaction, and the project
      activity feed; sources, runs, clarification and draft saves emit today (the backend half
      of SSPOC-45)
- [x] CI: secret scanning, job timeouts, PR title check; squash-only merges

## P0 product UI

Decided 2026-10-13: the POC includes the product UI from the v1 prototype
([docs/design/ScopeSteps-v1.html](../design/ScopeSteps-v1.html)), built against the live API with
none of its demo features. Each story has a backend and a frontend subtask; the order is under
[P0 build order](#p0-build-order).

- [x] Design system and app shell (SSPOC-26): design tokens in light, dark and system themes
      with an indigo or teal accent, bundled fonts, the sidebar and top bar, shared components,
      Appearance settings. Navigation lists only the screens that work today
- [x] Chat, Backlog, Sources and the evidence sheet moved into the new shell (SSPOC-51): the
      chat thread is built from the run's state (questions answered from the composer, Stop,
      findings with citations, the draft), the backlog has the All / Needs attention filter, and
      sources have a table, a source viewer and an Add sources modal. Controls follow the role
      from `/me`; limits come from the project detail
- [ ] Sign-in and sign-out with server-side sessions (SSPOC-27)
  - [x] Backend (SSPOC-28): password sign-in, session cookie, sign-out, seeded account per role
        ([ADR 0007](../adr/0007-password-sign-in-and-server-side-sessions.md)). Selected with
        `AUTH_MODE=session`; the default stays `local` (the seeded reviewer) until the frontend
        lands
  - [ ] Frontend (SSPOC-29): sign-in screen, session handling and sign out; flips the default
        to `AUTH_MODE=session`
- [ ] Create, switch and rename projects (SSPOC-30)
  - [x] Backend (SSPOC-31): project list with roles and scope status, create, revision-checked
        rename, and project detail with the configured limits
  - [ ] Frontend (SSPOC-32): project switcher, New project flow and Project settings
- [ ] Add and remove individual sources (SSPOC-33)
- [ ] Saved conversation with read-only, cited agent replies (SSPOC-36)
- [ ] Version history and compare (SSPOC-39)
- [ ] People named in sources, with corrections and confirmed decision rights (SSPOC-42)
- [ ] Activity log from append-only audit events (SSPOC-45)
  - [x] Backend (SSPOC-46): append-only events and the paged project activity feed
  - [x] Frontend (SSPOC-47): the Activity page in the sidebar, newest first with when, who and
        what, older entries on demand. The story closes once every action it lists emits its
        event (approval, edits, change decisions, people, rename, sign-in)
- [ ] Profile name, job title and about text; initials, no photo (SSPOC-48)
  - [x] Backend (SSPOC-49): `PATCH /me` with revision-checked name, job title and about, and
        `GET /projects/{id}/members` so the app can name who did what. Profile changes are not
        audited yet (see `modules/identity/README.md`)
  - [ ] Frontend (SSPOC-50): Profile and Account settings tabs
- [ ] See the version history and compare versions (SSPOC-39)
  - [x] Backend (SSPOC-40): `GET /projects/{id}/backlogs` (cursor-paged, with each version's
        decision) and `GET /projects/{id}/backlogs/compare` by stable item and criterion ids
  - [ ] Frontend (SSPOC-41): the version selector, history and compare view
- [x] Edit and approve baseline v1 (SSPOC-11)
  - [x] Backend (SSPOC-12): revision-checked draft item edits with human provenance, accept or
        reject agent suggestions, person-added criteria, `POST /review` with the four server
        checks, and approve/reject as one transaction with the audit event and a numbered
        baseline ([ADR 0008](../adr/0008-atomic-baseline-approval.md))
  - [x] Frontend (SSPOC-13): Edit story (title, text, criteria, add a criterion), Accept /
        Reject / Undo on agent suggestions, answering open or skipped decisions on the draft,
        and the approve modal with the server's checks, revision, hash, story count and
        approver. Approvers see Approve, editors see that it needs a Product owner, viewers read
        only; a stale revision asks for a reload. Starting a run warns when the draft in progress
        has edits. The version selector lists the draft and the current baseline until the
        versions list (SSPOC-40) lands
- [ ] Export an approved backlog as JSON or Markdown (SSPOC-20)
  - [x] Backend (SSPOC-21): `GET /backlogs/{version}/export?format=json|markdown` for any
        member, of the exact approved version with its approval metadata, escaped Markdown, safe
        download names and citations re-checked on every export
  - [ ] Frontend (SSPOC-22): the export modal with preview, Copy and Download

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

- Done: SSPOC-12, SSPOC-26, SSPOC-28, SSPOC-31 and SSPOC-46. SSPOC-43 is in progress.
- Ready now: SSPOC-51, SSPOC-29, SSPOC-32 and SSPOC-47 (frontend); SSPOC-15, SSPOC-21,
  SSPOC-34, SSPOC-40 and SSPOC-49 (backend); the SSPOC-25 Groq check.
- Bottlenecks: SSPOC-51 blocks the frontend of SSPOC-33, 36 and 11. SSPOC-13 blocks SSPOC-16,
  19, 22 and 41.
- Longest chain: SSPOC-51 → 33 → 36 → 14 → 17 → 23 → 24.
- SSPOC-34, SSPOC-37, SSPOC-43 and SSPOC-15 change the agent. Merge them one at a time and
  measure live only after asking. SSPOC-23 runs on the final prompt.

## P0 acceptance

Acceptance criteria from the [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md).

- [x] Upload two sources; stable source and block IDs (SSPOC-4)
- [x] Agent run with clarification (answer and skip) (SSPOC-7, SSPOC-8)
- [x] Evidence-backed draft backlog with source drawer (SSPOC-8)
- [x] Draft edits, review and approval into immutable baseline v1 (SSPOC-11, SSPOC-12,
      SSPOC-13)
- [ ] Change request producing a stable-ID diff; approve → v2, reject → v1 unchanged (SSPOC-14, SSPOC-17)
- [ ] Approved-only JSON/Markdown export (SSPOC-20): backend done (SSPOC-21), the export modal
      is SSPOC-22
- [ ] Evaluation against a single-pass baseline on held-out packs (SSPOC-23)
- [ ] End-to-end Playwright test of the full flow (SSPOC-24)

Update this page in the same pull request that changes a status.

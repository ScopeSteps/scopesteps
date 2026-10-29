# Roadmap and status

Last updated: 2026-10-27. Jira epic: SSPOC-1.

| Phase                     | Scope                                                                                                                                                                   | Status          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Foundation                | Monorepo, module skeleton, tooling, CI, docs                                                                                                                            | Done            |
| P0: POC                   | Text sources → clarification → cited backlog → approved baseline → one change diff → export; evaluated against a single-pass baseline; product UI from the v1 prototype | **In progress** |
| P1: Core platform         | Hosted deployment and single sign-on, durable worker, source audit hub, one-way Jira publishing                                                                         | Planned         |
| P2: Expanded intelligence | PDF/wiki/repository ingestion, evaluated retrieval, stakeholder profiles beyond the POC's People page, planning scenarios                                               | Planned         |
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
      open item on SSPOC-25, which closes after it. The 2026-10-14 run (12 drafts) did not
      confirm it: 7 valid, 3 calls cut off, because output budgets were sized from a pessimistic
      input estimate. With measured budgets, 7 of 7 drafts were valid with none cut off; 3 more
      drafts complete the run once the daily token limit allows
      ([ADR 0006](../adr/0006-groq-backup-provider.md) notes). The 2026-10-15 completion run
      (4 drafts) did not confirm it either: 2 valid; one run had both calls rejected against the
      schema, and one lost a completed draft when its targeted repair was `request_too_large`
      (suspected runner bug, evals/README.md). 9 of 11 drafts with the fix were valid
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
- [x] SSPOC-43 (backend half of SSPOC-42, PR #46): runs extract the people the
      sources name with role, citations and any stated decision right (prompt `draft-v6`, schema
      `draft-backlog.v4`); `projects` stores them with corrections and confirmed rights kept
      apart from the extraction, behind revision-checked, audited people routes; the dev packs
      list expected people
- [x] SSPOC-34 (backend half of SSPOC-33), implemented, PR pending: uploads of one or more files
      of any kind (brief, transcript, supporting document), each a new numbered source, all or
      none; a new-version route for corrected content; the word limit counts the project's
      current sources; guarded soft removal (`409 SOURCE_IN_USE` while a run, backlog version or
      person cites it, ADR 0009); runs pin any set of source versions with no prompt change
- [ ] Measure `draft-v6` on the dev packs against `draft-v4` (not yet measured live; ask first)
- [x] Measure `reply-v1` on the dev reply questions with `just evals-reply`: 2026-10-16, 30/30
      valid, every automatic verdict passed (18/18 cite, 6/6 ignore, 0 citations dropped); human
      verdicts on the 6 `unrecorded` replies are still open on the review sheet
- [x] CI: secret scanning, job timeouts, PR title check; squash-only merges
- [x] SSPOC-23: the final held-out comparison (2026-10-20): agent and single-pass on the same
      model, prompt and sources, and again with the final answers; change analysis on the
      held-out change requests; every verdict reviewed semantically; safety, failure and recovery
      scenarios mapped to tests; defects logged as SSPOC-83 to SSPOC-90
      ([POC evaluation](poc-evaluation.md), evals/README.md)
- [x] SSPOC-23: the critical flow as a Playwright test (`just e2e`) on a labelled replay of a
      recorded live run ([ADR 0018](../adr/0018-labelled-replay-of-a-recorded-run.md))
- [x] SSPOC-24: POC scope frozen 2026-10-20; setup verified from a clean clone with placeholder
      configuration and no secrets (2026-10-21); the demonstration script with live, replay and
      video modes ([docs/demo](../demo/README.md)); a labelled replay video as the recorded
      backup (attached to SSPOC-24); hosting and Jira publishing do not block the local demo
- [x] SSPOC-106: prompt sensitivity. `just evals-sensitivity` scores `draft-v10` against
      three reworded copies on the dev packs; 2026-10-26: no proven difference on any metric
      (evals/README.md)
- [x] SSPOC-107: five more dev packs (250 to 2,400 words, easy to hard, two with supporting
      documents) and a datasheet; sensitivity reports a paired bootstrap change from the
      original; 2026-10-26 rerun at 48 drafts per version: plain finds 2.3 points fewer
      requirements, no other proven difference (evals/README.md)

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
- [x] Sign-in and sign-out with server-side sessions (SSPOC-27)
  - [x] Backend (SSPOC-28): password sign-in, session cookie, sign-out, seeded account per role
        ([ADR 0007](../adr/0007-password-sign-in-and-server-side-sessions.md))
  - [x] Frontend (SSPOC-29): sign-in screen that returns to the page asked for, return to
        sign-in on any 401, sign out from the account menu and the Account settings, cached data
        dropped on the way out. `AUTH_MODE=session` is now the default; `just setup` generates
        the seeded accounts' password in `.env`
- [x] Create, switch and rename projects (SSPOC-30)
  - [x] Backend (SSPOC-31): project list with roles and scope status, create, revision-checked
        rename, and project detail with the configured limits
  - [x] Frontend (SSPOC-32): project switcher in the sidebar's project card, the two-step New
        project modal, Project settings (rename, limits and members, read-only for viewers), the
        home page listing projects by name, and the chat's three setup steps with their real
        state. Inviting members and changing roles wait for an API
- [x] Add and remove individual sources (SSPOC-33)
  - [x] Backend (SSPOC-34): uploads of any kind, the project-wide word limit and guarded soft
        removal (PR #48)
  - [x] Frontend (SSPOC-35): Add a source, from the Sources page and the chat composer's "+",
        uploads one or several files in one request, each with its kind, after a browser check
        of type and size; the server's answer is what is shown. The table labels sources `SRC-n`
        with kind, paragraph and word counts; the source viewer removes a source after
        confirmation or, on `SOURCE_IN_USE`, says what still refers to it. New project step 2
        (SSPOC-32) uses the same several-file picker. Revising a source through the versions route
        has no UI yet
- [ ] Saved conversation with read-only, cited agent replies (SSPOC-36)
  - [x] Backend (SSPOC-37), implemented, PR pending: one append-only conversation per project,
        paged by cursor; a message starts one leased, budgeted reply run with no tools whose
        claims cite source paragraphs or recorded answers, and unsupported claims are shown as
        the agent's own; answers can be changed until their version is approved; change
        requests start a change run (SSPOC-15)
        ([ADR 0010](../adr/0010-conversation-and-read-only-replies.md)). Prompt `reply-v1`
        measured live 2026-10-16 (30 of 30 replies, see evals/README.md)
  - [x] Frontend (SSPOC-38), implemented, PR pending: the chat renders the stored conversation
        (older pages on demand) with cited replies, question and decision cards and events; the
        composer sends messages and change requests (only with a baseline and no change in
        review), answers and changes answers until their version is decided, shows the API's
        length limit and turns Send into Stop while the agent works; failed sends stay to retry
- [x] Version history and compare (SSPOC-39)
- [ ] People named in sources, with corrections and confirmed decision rights (SSPOC-42)
  - [x] Backend (SSPOC-43): extraction, corrections and confirmed rights (PR #46)
  - [x] Frontend (SSPOC-44), implemented, PR pending: the People page in the sidebar, one card
        per person with role, rights, status tag and citations into the evidence sheet; editors
        correct a name and role in place and set Decides, Advises or Unknown; the badge counts
        people whose rights are neither stated nor confirmed
- [ ] Activity log from append-only audit events (SSPOC-45)
  - [x] Backend (SSPOC-46): append-only events and the paged project activity feed
  - [x] Frontend (SSPOC-47): the Activity page in the sidebar, newest first with when, who and
        what, older entries on demand. The story closes once every action it lists emits its
        event (approval, edits, change decisions, people, rename, sign-in)
- [x] Profile name, job title and about text; initials, no photo (SSPOC-48)
  - [x] Backend (SSPOC-49): `PATCH /me` with revision-checked name, job title and about, and
        `GET /projects/{id}/members` so the app can name who did what. Profile changes are not
        audited yet (see `modules/identity/README.md`)
  - [x] Frontend (SSPOC-50): Profile and Account settings tabs. Profile saves name, job title
        and about (live count, 409 asks for a reload); Account shows email, the role in the
        project in view and what it allows, and Sign out. Reviewers are named by their display
        names from the project's members
- [x] See the version history and compare versions (SSPOC-39)
  - [x] Backend (SSPOC-40): `GET /projects/{id}/backlogs` (cursor-paged, with each version's
        decision) and `GET /projects/{id}/backlogs/compare` by stable item and criterion ids
  - [x] Frontend (SSPOC-41): the Backlog version selector lists every version from the API and
        keeps the choice in the URL (an unknown id falls back to the latest version); approved
        versions read-only with approver, time and hash; the top-bar chip names the baseline or
        the one that superseded a past version; the Change requests page, with an empty request
        list until change requests land, compares any two approved versions with the server's
        added, changed and removed entries and the unchanged story count
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
        has edits
- [x] Export an approved backlog as JSON or Markdown (SSPOC-20)
  - [x] Backend (SSPOC-21): `GET /backlogs/{version}/export?format=json|markdown` for any
        member, of the exact approved version with its approval metadata, escaped Markdown, safe
        download names and citations re-checked on every export
  - [x] Frontend (SSPOC-22): Export on every approved version, for every member, opens the
        export modal: any approved version, JSON or Markdown, a read-only preview of exactly
        what the server returned, Copy (selecting the text when the clipboard is blocked) and
        Download under the server's filename. With no approved version it says only approved
        versions can be exported; a server refusal is shown as given. Markdown and the modal's
        JSON and Copy were replaced by the Jira CSV (SSPOC-61)
- [x] Export an approved backlog as a Jira-ready CSV (SSPOC-61). Decided 2026-10-16: the app
      exports CSV only (Issue ID, Issue Type, Summary, Description, Parent), JSON stays in the
      API with no UI, and Markdown is removed, a breaking contract change
      ([ADR 0014](../adr/0014-jira-csv-export.md))
  - [x] Backend (SSPOC-62): `format=csv|json` (`format=markdown` is a 422), epics before their
        stories, summaries cut to 255 characters at a word, formula-start cells neutralised,
        RFC 4180 bytes that never change for the same version, and no evidence, ids, hashes or
        approval details in the CSV
  - [x] Frontend (SSPOC-63): the export modal offers one "Download CSV for Jira" for any
        approved version and any member, with a table preview read from the downloaded file
        (descriptions on expand) and the server's refusals shown as given
- [x] Agent lookups and suggested actions in the conversation (SSPOC-55): `reply-v1` measured
      2026-10-16; next prompt `reply-v2` with read-only lookup tools and at most one suggested
      action a person confirms (needs a note on ADR 0010 and a new ADR)
  - [x] Backend (SSPOC-56): bounded tool loop in reply runs, typed suggestion checked in code,
        suggestion status on the message, dev-pack reply cases; live runs only after asking.
        In progress: prompt `reply-v2` with read-only lookups and the new reply cases, measured
        2026-10-16 against `reply-v1` (no proven difference, about 50% more cost; runs stay on
        `reply-v1`). Suggestions built 2026-10-16: prompt `reply-v3`, checks in code, status
        route, ADR 0013; measured 2026-10-17 and adopted: new reply runs pin `reply-v3`
  - [x] Frontend (SSPOC-57): lookup progress lines and suggestion cards that call the existing
        endpoints only when confirmed
- [ ] [STRETCH GOAL] Streamed replies and a rolling conversation summary (SSPOC-58), after P0
  - [ ] Backend (SSPOC-59): stream a reply step's events; summary step for older messages
  - [ ] Frontend (SSPOC-60): render streamed text, fall back to the run driver
- [x] See at a glance which backlog items are epics and which are stories (SSPOC-64)
  - [x] Frontend (SSPOC-65): Epics and stories, Decisions and Out of scope sections; each epic a
        card with an Epic tag and story count, each story a Story tag; no API change
- [x] Confirm who is who in an uploaded transcript (SSPOC-66). Decided 2026-10-16: speakers are
      detected by a parser, not a model, and an editor confirms each one's participant and
      meeting role; confirming never blocks a run (needs an ADR; superseded by ADR 0015 in
      SSPOC-77)
  - [x] Backend (SSPOC-67): detect speaker labels in transcripts and list them per source
  - [x] Backend (SSPOC-68): participants and speaker assignments in projects, revision-checked
        and audited
  - [x] Backend (SSPOC-69): confirmed speakers in the passages the agent reads; dev eval packs
        without inline roles; live runs only after asking
  - [x] Frontend (SSPOC-70): the Who's who step after a transcript upload
  - [x] Frontend (SSPOC-71): participants and unconfirmed speakers on People and Sources
- [x] Show confirmed speakers in change analysis and chat replies (SSPOC-72), after SSPOC-66
  - [x] Backend (SSPOC-73): prompts `change-v2` and `reply-v4` show who speaks in each
        transcript paragraph, as `draft-v7` does (PR #88); measured 2026-10-19 and adopted:
        new change runs pin `change-v2` and new reply runs `reply-v4`
- [x] Drafts quote only what was said, never who said it (SSPOC-75): new draft runs pin
      `draft-v10`, adopted 2026-10-20 after measuring it
  - [x] Backend (SSPOC-76): `draft-v9`, a quoting rule, was measured 2026-10-20 and not adopted
        (the attribute was quoted in 9 of 30 runs against 3 of 30). `draft-v10` (schema
        `draft-backlog.v5`, PR #98) lists speakers once as participants with ids and lets a person
        name one by id, so no quote proves identity; measured 2026-10-20 against `draft-v8`: every
        person found in all 30 runs (3 runs lost all their people before), no other group outside
        its interval (evals/README.md); adopted for new draft runs
- [x] Drafts give epics and stories fuller descriptions and acceptance criteria (SSPOC-80):
      `draft-v8`, measured against `draft-v7` 2026-10-19 (PR #96); not adopted on its own,
      runs get it as part of `draft-v10`
  - [x] Backend (SSPOC-81): prompt `draft-v8`, the `epic_without_criteria` check and the
        criteria-per-story and story-context eval metrics
  - [x] Frontend (SSPOC-82): an epic's acceptance criteria on its card, with suggestions
        reviewed there; descriptions keep their paragraphs
- [x] Identify the people in the transcripts before clarifying questions and drafting
      (SSPOC-77, ADR 0015): sources, then who's who, then the agent's questions (PR #93)
  - [x] Backend (SSPOC-78): a draft run starts only once every speaker is confirmed (409
        `SPEAKERS_UNCONFIRMED`); name-only sample transcript and API test fixture
  - [x] Frontend (SSPOC-79): an "Identify the people" step between sources and the run
- [ ] A change's before and after impact as a summary and chart, in the chat, on the Backlog
      and on Change Requests (SSPOC-92). Decided 2026-10-25: every figure comes from the code
      comparison of the two versions, never from the model
  - [x] Backend (SSPOC-95), PR pending: each change request with a candidate returns its
        `impact` (epics, stories and criteria before and after; added, changed, removed and
        unchanged; scope decisions raised), counted when it is read so it follows a rejected
        suggestion; `change.ready_for_review` and `change.no_change_needed` name their request,
        and the thread returns the same impact beside `change.ready_for_review`
        ([ADR 0011](../adr/0011-change-requests-and-stable-id-change-sets.md) notes)
  - [x] Frontend (SSPOC-96), PR pending: an impact panel (a plain-language summary, a
        before-and-after bar chart per kind of work with a text alternative, and the figures as
        text) on the Backlog page for a candidate in review and on each change request, above the
        existing lists; the chat's finished analysis shows the summary with "View in Backlog" and
        "View in Change Requests", which brings that request into view
- [ ] Talk a change through with the agent before requesting it (SSPOC-91). Decided 2026-10-25:
      a discussion is a read-only reply that weighs a proposed change against the baseline and may
      only offer the existing change-request suggestion
  - [x] Backend (SSPOC-93), PR pending: `discuss` messages, which need a baseline, get reply runs
        pinned to `reply-v5` (`reply-v4` plus discussion rules; `reply-v4` was already taken).
        The reply reads the labelled baseline, keeps up to 10 claims, loses any claim naming a
        label it was not shown, and offers only a change request; free messages keep `reply-v4`
        ([ADR 0013](../adr/0013-suggested-actions-in-replies.md) notes). The dev reply questions
        gain discuss cases, measured live before adoption (evals/README.md)
  - [ ] Frontend (SSPOC-94): the composer offers Talk it through and Request a change, each with
        a one-line explanation, once a baseline is approved

Approval, change review and export (SSPOC-11 to SSPOC-22) follow the prototype's screens: the
approve modal with server checks, change requests from the chat with a scope decision, the Change
requests page and the export modal.

## P0 build order

Mirrors the [build-order comment on SSPOC-1](https://scopesteps.atlassian.net/browse/SSPOC-1?focusedCommentId=10052)
and the "blocks" links in Jira; change both together. One row per story or task. Rows with the
same stage can run in parallel. A row moves on once everything in "Waits on" is done, and a
backend subtask with no blockers can start before its stage.

| Stage | Ticket          | Delivers                                                   | BE · FE             | Waits on                                                               | Unblocks         |
| ----- | --------------- | ---------------------------------------------------------- | ------------------- | ---------------------------------------------------------------------- | ---------------- |
| 1     | SSPOC-26 (task) | Design system and app shell                                | FE only             | Nothing                                                                | Every FE ticket  |
| 2     | SSPOC-51        | Today's screens in the new shell                           | FE only             | 26                                                                     | FE of 33, 36, 11 |
| 2     | SSPOC-27        | Sign in and out (needs an ADR)                             | 28 · 29             | BE: nothing; FE: 28, 26                                                | 48               |
| 2     | SSPOC-30        | Create, switch and rename projects                         | 31 · 32             | BE: nothing; FE: 31, 26                                                | —                |
| 2     | SSPOC-45        | Activity log from audit events                             | 46 · 47             | BE: nothing; FE: 46, 26                                                | 11, 17           |
| 2     | SSPOC-42        | People and decision rights (prompt change)                 | 43 · 44             | BE: nothing; FE: 43, 26                                                | 23               |
| 3     | SSPOC-48        | Profile                                                    | 49 · 50             | BE: 28; FE: 49, 26                                                     | —                |
| 3     | SSPOC-33        | Add and remove single sources (may change prompt)          | 34 · 35             | BE: nothing; FE: 34, 26, 51                                            | 36               |
| 3     | SSPOC-11        | Edit and approve baseline v1 (the main gate)               | 12 · 13             | BE: 46; FE: 12, 26, 51                                                 | 39, 20, 14, 17   |
| 3     | SSPOC-64        | Epics and stories labelled in the backlog                  | FE only (65)        | FE: 26, 51                                                             | —                |
| 3     | SSPOC-66        | Who's who in transcripts (needs an ADR, changes the agent) | 67, 68, 69 · 70, 71 | BE: 67 nothing, 68 on 67, 69 on 68; FE: 70 on 68, 26, 51; 71 on 68, 70 | —                |
| 4     | SSPOC-72        | Confirmed speakers in change runs and replies (prompts)    | BE only (73)        | BE: 69                                                                 | —                |
| 5     | SSPOC-75        | Drafts name speakers by id (prompt `draft-v10`)            | BE only (76)        | BE: 73                                                                 | —                |
| 4     | SSPOC-77        | People before questions (ADR 0015)                         | 78 · 79             | BE: 69; FE: 78, 70                                                     | —                |
| 4     | SSPOC-36        | Saved conversation, cited replies (needs an ADR)           | 37 · 38             | BE: 34; FE: 37, 26, 51                                                 | 14, 23           |
| 4     | SSPOC-39        | Version history and compare                                | 40 · 41             | BE: 12; FE: 40, 13                                                     | —                |
| 4     | SSPOC-20        | JSON and Markdown export                                   | 21 · 22             | BE: 12; FE: 13                                                         | 23               |
| 5     | SSPOC-14        | Change request and stable-ID diff                          | 15 · 16             | BE: 12; FE: 15, 13, 38                                                 | 17               |
| 5     | SSPOC-61        | Jira-ready CSV export (breaking, needs an ADR)             | 62 · 63             | BE: 21; FE: 62, 22                                                     | —                |
| 6     | SSPOC-17        | Approve a change as v2 or reject it                        | 18 · 19             | BE: 15, 12, 46; FE: 18, 16, 13                                         | 23               |
| 6     | SSPOC-55        | Agent lookups and suggested actions (prompt)               | 56 · 57             | BE: 37, 15; FE: 56, 38                                                 | 58               |
| 7     | SSPOC-23 (task) | Held-out evaluation, safety and recovery tests             | —                   | 17, 20, 36, 43                                                         | 24               |
| 7     | SSPOC-58        | [STRETCH GOAL] Streamed replies, rolling summary           | 59 · 60             | BE: 56; FE: 59, 57                                                     | —                |
| 8     | SSPOC-24 (task) | Setup, end-to-end test and demo                            | —                   | 23 and every UI story                                                  | —                |

- Done: SSPOC-12, SSPOC-26, SSPOC-28, SSPOC-31 and SSPOC-46. SSPOC-43, SSPOC-34 and SSPOC-37
  are implemented, PR pending. SSPOC-19 is implemented, PR pending, which completes story
  SSPOC-17 with SSPOC-18.
- Ready now: SSPOC-51, SSPOC-29, SSPOC-32 and SSPOC-47 (frontend); SSPOC-15, SSPOC-21,
  SSPOC-40 and SSPOC-49 (backend); the SSPOC-25 Groq check.
- Bottlenecks: SSPOC-51 blocks the frontend of SSPOC-33, 36 and 11. SSPOC-13 blocks SSPOC-16,
  19, 22 and 41.
- Longest chain: SSPOC-51 → 33 → 36 → 14 → 17 → 23 → 24.
- SSPOC-34, SSPOC-37, SSPOC-43 and SSPOC-15 change the agent (SSPOC-43 moves runs to `draft-v6`
  and SSPOC-37 adds `reply-v1`, neither measured live yet). Merge them one at a time and measure live only after asking. SSPOC-23
  runs on the final prompt.
- SSPOC-56 changes the agent (`reply-v2`): merge it on its own (`reply-v1` was measured
  2026-10-16). SSPOC-58 is a stretch goal for after P0. SSPOC-62 removed `format=markdown`, a
  breaking contract change whose only consumer was the web app.
- New and waiting on nothing: SSPOC-65 (backlog labels, frontend) and SSPOC-67 (speaker
  detection, backend).
- SSPOC-69 changes the agent (confirmed speakers in the passages it reads) and reworks the dev
  eval packs: merge it on its own and measure live only after asking. If it merges after
  SSPOC-23, SSPOC-23 runs again.
- SSPOC-73 changes the agent (new change and reply prompt versions): merge it on its own and
  measure live only after asking. If it merges after SSPOC-23, SSPOC-23 runs again.

## P0 acceptance

Acceptance criteria from the [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md).

- [x] Upload two sources; stable source and block IDs (SSPOC-4)
- [x] Agent run with clarification (answer and skip) (SSPOC-7, SSPOC-8)
- [x] Evidence-backed draft backlog with source drawer (SSPOC-8)
- [x] Draft edits, review and approval into immutable baseline v1 (SSPOC-11, SSPOC-12,
      SSPOC-13)
- [x] Change request producing a stable-ID diff; approve → v2, reject → v1 unchanged (SSPOC-14, SSPOC-17)
  - [x] Backend (SSPOC-15), implemented, PR pending: change requests recorded before analysis,
        a change run proposing a stable-id change set saved as a candidate in review beside an
        unchanged baseline, scope decisions for reversals, `no_change_needed`, and a paged list
        of requests with added, changed and removed counts
        ([ADR 0011](../adr/0011-change-requests-and-stable-id-change-sets.md)). Prompt
        `change-v1` first measured live 2026-10-19; runs now use `change-v2`
  - [x] Backend (SSPOC-18), implemented, PR pending: an approver records reverse or keep on
        each scope decision; approving a candidate freezes it as v2 and advances the baseline,
        rejecting it leaves v1, and the change request moves to approved or rejected, in one
        audited transaction
  - [x] Backend (SSPOC-53), implemented, PR pending: the decision posts `change.approved` or
        `change.rejected` to the conversation in the same transaction, naming the request and
        the resulting baseline version; the change request names the version its approval
        produced; an approver answers a candidate's other open decisions (such as a skipped
        clarification) so it can be approved
  - [x] Frontend (SSPOC-16), implemented, PR pending: the change analysis, the change run's
        questions and the scope-decision card in the chat (Yes or No for an approver, who must
        decide for everyone else); the candidate on the Backlog page with its stable ids, added,
        changed and removed tags, the Changes only filter and the exclusion removed if reversed;
        the Change requests page listing every request with its status, summary, conflict and
        outcome
  - [x] Frontend (SSPOC-19), implemented, PR pending: Reject and Approve as v2 on the
        candidate for an approver, Approve disabled until the scope decision is made and every
        check passes (the approve modal adds a "Scope decision made" check), only Reject after a
        keep, a reload and another review on a stale baseline, and the outcome in the chat and on
        the Change requests page
  - [x] Frontend, PR pending (2026-10-15): an approver answers a candidate's other open
        decisions on the Backlog page, so a change run's question no longer leaves only
        rejection; a rejected candidate is named as one
  - [x] Change-flow polish from the 2026-10-15 end-to-end run (SSPOC-54; story SSPOC-52 done
        with SSPOC-53 and the item above), implemented, PR pending: the project's scope state
        reloads when a run stops working, so the chat no longer shows a false "Locked" note and
        the header moves on; `change.approved` and `change.rejected` appear in the chat as the
        one place the outcome is told, linking to the new baseline and the Change requests page,
        which names an approved request's version; a non-approver sees who must answer a
        candidate's open decision, and a rejected candidate links to its change request; copy
        fixes for reversed exclusions, rejected reversals and skipped questions answered later
        on the backlog
- [x] Approved-only export: JSON in the API, a Jira CSV in the app (SSPOC-20, SSPOC-61)
- [x] Evaluation against a single-pass baseline on held-out packs (SSPOC-23,
      [POC evaluation](poc-evaluation.md))
- [x] End-to-end Playwright test of the full flow (built with SSPOC-23, `just e2e`)

Update this page in the same pull request that changes a status.

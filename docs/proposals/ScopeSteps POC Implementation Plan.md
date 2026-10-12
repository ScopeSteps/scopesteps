# ScopeSteps POC Implementation Plan

Version 0.1 | 10 October 2026 | One-week milestone plan, not a delivery guarantee

**Purpose:** prove traceable scoping and controlled change using the same React/FastAPI/Python foundation intended for the full platform. This is the first milestone, not a replacement for the platform vision. Companion documents: [Project Proposal](ScopeSteps%20Project%20Proposal.docx) and [Technical Proposal](ScopeSteps%20Technical%20Proposal.md). The Markdown edition is the source for the matching Word edition.

## Part A. High-level plan

### 1. Objective and research question

> Given a project brief and meeting transcript, ScopeSteps asks useful clarification questions, drafts an evidence-backed backlog, saves a human-approved baseline, and proposes a controlled diff for one new scope request.

Research question: does a bounded agent with targeted clarification produce more accurate, traceable scope decisions than a single-pass assistant? The POC must demonstrate decisions and verification, not simply a high volume of generated tickets. No claim of production reliability, market advantage, reliable scheduling, or legal authority is implied.

### 2. Scope contract

| Include | Deliberately defer |
| --- | --- |
| React/TypeScript UI, FastAPI application and one Python agent | Multiple agents, a custom foundation model, or separate Node/Go backend |
| One project; one transcript + one brief in TXT/Markdown | PDF/OCR, audio, wiki and repository connectors |
| Source blocks and clickable citations; explicit suggestions/assumptions | Vector database, enterprise search and organizational memory |
| Up to two epics and eight stories with testable acceptance criteria | Initiatives, tasks/subtasks/bugs, staffing, timelines and ROI |
| Targeted clarification with saved answers | Full conversational workspace and inferred stakeholder authority |
| Human review, edits, approved baseline and one change-request diff | Complex collaborative editing and two-way Jira sync |
| Approved JSON/Markdown exports and a repeatable evaluation | Polished graph editor and public production launch |

Output limits are ceilings, not quotas. The model must not invent work to fill them. Inputs: two initial UTF-8 files, each at most 512 KiB, with 6,000 words combined. Clarification/change text is separately bounded; proposed default maximum 2,000 characters per answer/request. Source revisions remain explicit.

### 3. User journey and demo

![POC workflow](docs/diagrams/poc_workflow.svg.png)

1. Upload the project brief and transcript; display filenames, source IDs and paragraphs.
2. Start a run. The agent distinguishes decisions, suggestions, exclusions and unknowns; it may retrieve context or ask questions.
3. Answer or skip questions. A skipped decision remains unknown, not an invented default.
4. Review draft epics/stories, criteria, assumptions and supporting passages. Edit, reject or accept proposed details.
5. Approve the exact reviewed revision. Save immutable baseline v1.
6. Submit one change request. Analyze against v1 and display added/modified/removed items and open decisions.
7. Approve or reject the candidate. Approval creates v2; rejection leaves v1 untouched. Export an approved version.

Demo domain: campus room booking. The brief permits individual bookings, the transcript excludes recurring reservations from the first release, and cancellation rules are missing. Initial generation must exclude recurring bookings and ask about cancellation. After v1 approval, request weekly recurring reservations. The agent must identify the earlier exclusion, ask whether the authorized reviewer intends to reverse it, expose conflict-handling/cancellation questions, and propose a targeted diff. It must not silently replace v1 or invent calendar dates/costs.

### 4. Roles and safety boundary

Local POC: one seeded reviewer with Editor + Approver permissions, documented as a solo-demo simplification. The application, not the model, performs approval. Developer-local identity is permitted only when bound to loopback; public deployment requires real JWT authentication and an allowlist, or it is not deployed.

Use synthetic/de-identified sources only. Uploaded text is data, not executable instructions. Model tools cannot approve, publish, delete approved versions, read unrelated projects, or change permissions. Store secrets server-side. Show unresolved conflicts as blockers for affected items; do not claim a valid citation guarantees correct interpretation.

### 5. Required deliverables and completion gate

| Deliverable | Observable acceptance condition |
| --- | --- |
| Complete web flow | Upload → clarify → draft → inspect evidence → approve → request change → review diff → approve/reject → export. |
| Evidence-backed backlog | Source references resolve to exact stored passages; AI-added details are labeled and require review. |
| Version safety | Baseline survives rejected changes, refresh and restart. Unrelated approved items retain stable IDs/content. |
| Agent behavior | At least one scenario demonstrates evidence lookup or clarification that affects the resulting scope. |
| Evaluation | Report baseline comparison, failures, human corrections, latency and model usage on held-out examples. |
| Reproducibility | Setup instructions, locked dependencies, placeholder environment file and resettable synthetic fixtures. |

No unauthorized approval/export or baseline overwrite is acceptable. Model-quality findings are measured and reported, not hidden behind a claim of 100% accuracy. Jira and cloud deployment are optional, not prerequisites for completing the local POC.

### 6. Deadline checkpoints and ownership

Assign actual team members to Frontend, Backend/Agent, and Evaluation/Integration responsibilities; one person may cover multiple responsibilities. These are deadline checkpoints, not effort estimates or guarantees.

| Checkpoint | Required outcome / cut rule |
| --- | --- |
| Day 1 | Agree schema, input limits, annotated demo, provider/account access and API contract. Scaffold React/FastAPI; run one model tool-call/schema probe. |
| Days 2–3 | Upload/paragraph IDs, baseline single-pass generation, bounded clarification loop and source viewer work end to end. |
| Day 4 | Editable draft, approval checks, immutable baseline, reload/restart persistence. |
| Day 5 | One change request, stable-ID diff, rejection/approval behavior and approved export. |
| Days 6–7 | Held-out/adversarial tests, fixes, measured comparison, recorded backup demo and presentation. Freeze scope. |

If behind: cut visual polish, cloud hosting, and Jira first. Keep evidence, approval, version safety and the one change scenario. Do not call hardcoded responses live agent behavior. If live inference is unavailable, a labeled replay can illustrate the UI, but the AI capability remains unverified until a live run is recorded.

## Part B. Technical implementation

### 7. Minimal architecture

| Layer | POC choice |
| --- | --- |
| Frontend | React + TypeScript + Vite + Tailwind; normal list/cards and forms rather than a graph editor. |
| Backend | Python + FastAPI + Pydantic; modular application, no microservices. |
| Agent | Thin tool-calling harness around one provider SDK; typed tools, durable run records and hard iteration limits. |
| Data | SQLAlchemy + Alembic; local SQLite. Hosted option uses external PostgreSQL and never ephemeral host disk. |
| Retrieval | Stable source blocks and simple text lookup; complete small inputs can also fit in model context. |
| Tests | pytest for backend; frontend unit tests and Playwright for the critical browser flow. |
| Model | Evaluate a Gemini API free-tier candidate first using synthetic data. Exact model ID is selected by Day 1 tests, not assumed in advance. |

Use the module and API names in the Technical Proposal to avoid a throwaway implementation. Pin compatible, established dependency versions; no new framework should be added without a concrete need.

### 8. Screens and component behavior

Three primary views suffice: (1) Sources + project summary; (2) Agent run/clarification + editable backlog + evidence drawer; (3) Scope-change diff + approval/export. Display run state and errors explicitly. Refresh restores by run/version ID. Disable duplicate UI actions while requests are in flight, but enforce duplicate protection on the server too.

Source drawer shows document/version, paragraph, quotation and claim origin. Review controls operate on the exact revision loaded. Diff identifies stable item IDs; a text comparison alone must not imply that an unrelated rewritten item is the same requirement. Human edits are retained and labeled.

### 9. Minimum persistent records

| Record | Fields needed initially |
| --- | --- |
| Project | ID, name, current approved version ID, local reviewer identity |
| SourceVersion + SourceBlock | IDs, project, version/checksum, text, paragraph locator, origin/actor/time, access classification |
| AgentRun + RunStep | IDs, pinned input/baseline versions, status/stage, revision/lease, model/prompt version, counters, result/error |
| Clarification | Run/question ID, question/context, answer/skip state, actor/time, evidence block ID |
| BacklogVersion + ItemRevision | Version/base/revision/hash/state; stable item IDs, parent, criteria, assumptions, blockers, human edits |
| EvidenceLink | Claim/criterion ID, source version/block, exact quotation/offset, supporting/conflicting relationship |
| ChangeRequest + Diff | Request text as source evidence; base version/hash; add/modify/remove operations and rationale |
| Approval + AuditEvent | Version/hash, actor/permission, action and timestamp |

Store small source text in the database; no object-storage integration is required initially. Save generated payloads as validated, schema-versioned JSON while retaining IDs/version/status fields relationally. A unique step identity prevents a retried request from committing a second draft. Version checks prevent stale approvals.

### 10. API slice

All routes use `/api/v1`; project authorization is required even in the simplified local actor implementation.

| Endpoint | Behavior |
| --- | --- |
| POST /projects/{id}/sources | Validate two supported file types and limits; return source/version IDs and blocks. |
| GET /projects/{id}/sources/{version}/blocks | Return authorized source blocks for the evidence drawer. |
| POST /projects/{id}/runs | Create initial/change run with pinned source/baseline versions; return run ID. |
| POST /runs/{id}/advance; GET /runs/{id} | Execute one bounded step; return persisted progress, questions or candidate ID. |
| POST /runs/{id}/answers | Save answer/skip as evidence and resume without resetting usage limits. |
| GET /projects/{id}/backlogs/{version} | Load draft/baseline, evidence references, revision and optional diff. |
| PATCH /backlogs/{version}/items/{item} | Draft-only allowed field edits; require expected revision. |
| POST /backlogs/{version}/review | Domain/reference checks; mark ready for explicit approval or return blockers. |
| POST /backlogs/{version}/approve or /reject | Check role, exact revision/hash and current baseline; commit atomically. |
| GET /backlogs/{version}/export?format=json | Approved JSON or Markdown; include permitted evidence identifiers and assumptions. |

Use Idempotency-Key on mutating commands; same key with different content returns 409. Return 409 for stale baseline/revision, 413 for oversized input, 415 for unsupported types, 422 for invalid schemas, and 429/503 for quota/provider failures. Error messages include request ID and retryability, not secrets or raw sensitive text. The Technical Proposal defines the full error envelope and platform endpoints.

### 11. Agent loop and limits

Tool set: `lookup_source`, `request_clarification`, `validate_backlog`. Source lookup is read-only and project-scoped. Drafting returns structured content; the domain service persists it. Approval and publishing are not model tools.

Initial limits: six model turns, eight tool calls, two clarification rounds per run, one schema-repair attempt; configure output-token and spending limits. Use a bounded network timeout compatible with the selected host; test it during the provider probe. Answers resume the run without resetting limits. On exhaustion, return an explicit incomplete/needs-review state or failure with saved progress, not an invented answer.

Run states: created → running → waiting_for_input or ready_for_review; failed/cancelled are explicit exits. Execute one request-driven step at a time, guarded by a database lease/revision. Call the provider outside the DB transaction, validate, then commit only against the expected state. Browser advancement may stop when the tab closes; the saved run can resume. After a lost inference response, retry can incur extra billing; it must not duplicate an accepted draft.

Context includes the project policy, original source versions, authorized excerpts, confirmed answers, and the exact baseline for change mode. Prompt policy requires statement classification, source citations, unresolved questions and proposed-detail labels. Do not infer decision rights, engineering feasibility, dates or price. The provider adapter makes no silent paid/provider fallback.

### 12. Validation and version rules

Check schema types, item count/parents, unique IDs, reference ownership, quoted-text existence, dependency endpoints/cycles, forbidden operations, missing decisions and candidate/base version. Semantic support is reviewed by humans; a second model is not the only judge.

Approval is an application transaction: verify role and blockers → compare current baseline + candidate revision/hash → freeze candidate → record approval/audit → update project's current baseline. Further edits fork a new draft. A scope-change run proposes operations; it does not mutate v1. Rejection leaves the baseline pointer unchanged. Restoring an older version is a new reviewed version, not history deletion.

### 13. Model, environment and deployment setup

Local environment: React dev server, FastAPI bound to 127.0.0.1, SQLite file outside temporary directories, synthetic fixtures and a server-side provider key. Use .env.example placeholders and git-ignore the real .env/database. The POC's future README should document install/migrate/seed/start/test commands once code exists; no runnable app is claimed by this proposal.

Minimum settings: `APP_ENV`, `AUTH_MODE`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `MODEL_PROVIDER`, `MODEL_ID`, provider key, `RUN_MAX_TURNS`, `RUN_MAX_TOOLS`, `RUN_MAX_OUTPUT_TOKENS`, `RUN_COST_LIMIT`, `PROJECT_COST_LIMIT` and source size/word limits. VITE_API_BASE_URL is public; model/database secrets must not be VITE_ variables.

Hosted optional demo: Cloudflare Pages frontend, Render Free API and Supabase Free Postgres/Auth. Enforce JWT validation and an account allowlist; keep only synthetic inputs. Render sleeps after inactivity and loses local files on restart/spin-down. Supabase has quotas and can pause inactive projects. Persist all source/run/version state in the external database. Render's free Postgres expires after 30 days, so do not use it as the project archive. No reliable unattended worker is assumed on a free web service. [S2][S3][S4]

Model choice: Gemini's free tier is model/quota dependent and its pricing terms indicate free-tier data may be used to improve products. OpenRouter free variants and local Ollama are evaluated alternatives, not guaranteed equivalent drop-ins. Claude/OpenAI/Kimi APIs are treated as metered unless confirmed credits exist. Keep a tested local demonstration and recorded backup; no secret or confidential company document is required. AWS architecture/cost considerations belong to the platform technical document, not the POC critical path. [S1][S5]

### 14. Tests and evidence to collect

Use three to five small annotated project packs; reserve at least two for held-out evaluation. Include a rejected feature, ambiguous requirement, conflicting source, prompt-injection passage, and a change to an approved baseline. Test unauthorized/unknown project IDs even with seeded access. If time permits, repeat runs to expose variability rather than relying on one favorable result.

| Test | Expected outcome |
| --- | --- |
| Initial campus-booking scenario | Approved reservations captured; recurring bookings excluded; cancellation question surfaced. |
| Answer and skip | Answer becomes evidence; skipped material decision remains unresolved/blocking. |
| False citation or invalid parent | Validation fails or bounded repair occurs; no silent acceptance. |
| Prompt injection in transcript | No permission change, secret access, external publishing or bypassed approval. |
| Refresh / restart / repeated request | Saved state reloads; committed candidate is not duplicated; expired lease is recoverable. |
| Human edit and stale revision | Human change preserved; stale edit/approval rejected with conflict. |
| Add recurring reservations | Original exclusion identified; reversal requires human decision; targeted diff preserves unaffected work. |
| Reject or approve change | Reject leaves v1 intact; approve creates v2 with actor, evidence and hash. |
| Provider quota/outage | User sees recoverable error and counters; no infinite retry or silent paid fallback. |
| Export | Only approved version exports; references resolve and output does not expose unauthorized sources. |

Comparison: same model/configuration and original sources for single-pass versus agent. Also give final clarification answers to the baseline in a second comparison so improvements are not attributed solely to an information advantage. Annotate confirmed requirements and expected change impacts, not exact story wording.

Report: requirement coverage, unsupported commitment count/rate, citation support accuracy, conflict-handling outcomes, changed-item correctness, unintended baseline edits, human correction count/time, latency, turns, tokens and estimated/measured cost. Source-support judgments use human review. Findings from a small synthetic benchmark are limited and must be stated as such.

### 15. Optional Jira and platform carry-forward

Jira is one stretch item only if core acceptance passes and sandbox credentials/field configuration are available early. Publish approved stories/epics to one project after explicit confirmation; discover issue types/required fields, create parents first and record external IDs. Handle partial failure and ambiguous creation timeout visibly. No webhooks, two-way sync or changing Jira's hierarchy. JSON/Markdown export remains the fallback. [S6]

Reusable platform foundations: React routes/components, FastAPI contracts, provider interface, typed tools, source/block IDs, evidence model, approval/version service, change diff and evaluation fixtures. Later replace local storage/auth and request-driven execution with hosted identity, PostgreSQL/object storage and durable workers. Do not rewrite the product just to add a framework; preserve domain invariants and contracts.

### 16. References and unresolved setup choices

- S1: [Gemini API pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing).
- S2: [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/).
- S3: [Render Free restrictions](https://render.com/docs/free).
- S4: [Supabase pricing](https://supabase.com/pricing) and [JWT validation](https://supabase.com/docs/guides/auth/jwts).
- S5: [Full provider comparison and harness design](ScopeSteps%20Technical%20Proposal.md).
- S6: [Jira create-issue metadata/API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).

Confirm before coding: team owners; college rubric; exact model ID, quota and optional spending ceiling; local versus authenticated hosted demo; and whether Jira is mandatory. These are setup decisions, not permission to expand the one-week scope. The original proposal remains unchanged; this plan defines only milestone P0.

# ScopeSteps Technical Proposal

Version 0.1 | 10 October 2026 | Architecture proposal, not an implemented-system claim

**Purpose:** implementation blueprint for the full ScopeSteps platform, with explicit POC boundaries. Audience: student engineering team, technical reviewers, and project sponsor. Companion documents: [Project Proposal](ScopeSteps%20Project%20Proposal.docx) and [POC Implementation Plan](ScopeSteps%20POC%20Implementation%20Plan.md).

**Decision labels:** Confirmed = agreed product/technology direction; Recommended = proposed implementation default; Validate = needs a spike, account check, or stakeholder decision. Targets below are acceptance goals, not measured results. Source/pricing review date: 10 October 2026; recheck before deployment.

## 1. Architecture decisions

| Decision | Status and rationale |
| --- | --- |
| React + TypeScript frontend | Confirmed. Recommend Vite, Tailwind, React Router, and a typed API client. A dashboard does not need server rendering; Next.js remains an alternative only if the team has a concrete need. |
| Python agent and FastAPI backend | Confirmed. One language for application logic, tool schemas, and AI orchestration. Do not add Node.js/Go services without a demonstrated boundary or scaling need. |
| Modular monolith | Recommended. Separate domain modules, not separate microservices. API and later worker processes share the Python package and schemas. |
| Persistence | Recommended. SQLAlchemy + Alembic; SQLite for local POC, PostgreSQL for hosted/core platform. Test both database dialects before claiming portability. |
| Documents and retrieval | Recommended. POC stores small normalized text in the database. Platform stores originals in private object storage; PostgreSQL stores versions, blocks, ACLs, and metadata. Add pgvector only after retrieval evaluation justifies embeddings. |
| Agent orchestration | Recommended. Thin, explicit Python harness first; LangGraph with persistent checkpoints when multi-step resumability or branching warrants it. One agent, not separate PO/architect/lead agents. |
| Model | Validate. Gemini free-tier candidate using synthetic data; exact model chosen through tool-call and evidence tests. Adapter supports a separately approved alternative provider. |
| Identity | Recommended. Supabase Auth for hosted capstone; FastAPI validates JWTs and enforces application memberships. Local-only seeded identity is permitted solely in development. |
| Jobs | Recommended. POC uses bounded request-driven steps with durable state. Platform uses Celery + Redis workers, backed by database job records and an outbox. Redis is not the system of record. |
| Deployment | Recommended. Local first; optional Cloudflare Pages + Render Free + Supabase demo. AWS is a later paid/credit-funded alternative, not assumed free production hosting. |

Dependency versions must be selected at implementation time, published at least seven days earlier where feasible, and locked in npm/Python lockfiles. Validate compatibility rather than copying today's newest version.

## 2. System boundaries and product invariants

ScopeSteps supports product ownership, technical planning, and engineering coordination. It does not inherit a stakeholder's organizational authority. Business approvals, legal interpretations, engineering feasibility, and forecasts remain reviewable human decisions.

- Discussion is not commitment. Preserve confirmed decisions, proposals, exclusions, rejected ideas, assumptions, and open questions.
- A model may propose; application policy decides whether an operation is allowed. No model tool grants approval, changes permissions, or publishes independently.
- Every approved version is immutable. Editing creates a new draft; an authorized approval advances the current baseline atomically.
- Evidence refers to a specific source version and location. A quotation existing in a document does not establish that it supports the claim.
- Project/workspace isolation applies to retrieval, citations, runs, exports, and connector jobs, not only screens.
- Technical suggestions and estimates identify inputs, uncertainty, and verification status; insufficient inputs produce an explicit unknown.
- Rejected ideas are not resurrected without a new, authorized scope decision. No requirement is invented to fill an output quota.

![System architecture](docs/diagrams/system_architecture.svg.png)

## 3. Application modules and boundaries

| Module | Responsibilities and public boundary |
| --- | --- |
| Identity and access | Users, memberships, roles, decision rights, project access; authorize every service call. |
| Projects and stakeholders | Project brief, goals, participant profiles, role-confirmation status, decision-rights matrix. No inferred authority scores. |
| Sources | Upload/connectors, validation, immutable versions, blocks, source access rules, lifecycle and deletion. |
| Retrieval and evidence | Authorized text search, later hybrid retrieval, exact-reference validation, evidence viewer and stale-source flags. |
| Requirements and backlog | Statement classification, requirements, epics/stories/tasks, acceptance criteria, dependency graph, duplicates, versions. |
| Agent runs | Provider adapter, bounded tool loop, checkpoints, clarification, validation, failure recovery and usage accounting. |
| Changes and approvals | Baselines, candidate changes, semantic diff, impact notes, approval records, rejection and stale-version conflicts. |
| Integrations | Credential references, project field mappings, publishing outbox, external IDs, webhook inbox, reconciliation. |
| Planning | Later scenario estimates using explicit effort/capacity/cost inputs; engineering verification records. |
| Audit and operations | Business audit events, redacted telemetry, retention jobs, evaluation runs and budget enforcement. |

Proposed code layout:

```text
apps/web/src/{routes,features,components,api,auth}
apps/api/scopesteps/{api,auth,projects,sources,retrieval,backlog,changes}
apps/api/scopesteps/{agent,integrations,jobs,audit,planning}
apps/api/scopesteps/agent/{harness,providers,tools,schemas,policies}
apps/api/migrations
packages/contracts/openapi.json
tests/{unit,integration,e2e,fixtures,evals}
deploy/{local,demo,aws}
```

FastAPI's OpenAPI schema is the frontend contract; generate TypeScript types from it. Runtime validate untrusted browser/model payloads. API routes call domain services; tools call the same services with a restricted actor, never bypassing authorization through direct SQL.

## 4. Users, decision rights, and permissions

Personas: project lead/PO (scope operator), stakeholder (source contributor), engineer (technical reviewer), approver (business decision owner), integration administrator (connector operator), and assessor/viewer. A persona is not automatically a permission role.

| Role | Allowed | Explicit boundary |
| --- | --- | --- |
| Viewer | Read permitted project sources, approved versions and evidence | No source upload, editing, approvals, or connector administration. Restricted sources remain hidden. |
| Editor | Upload permitted sources, start runs, answer questions, edit/propose drafts and changes | Cannot approve unless also explicitly assigned Approver for the subject. |
| Approver | Review/reject and approve an exact candidate version for assigned decision subjects | Must possess project/source access; editing after review invalidates that approval. |
| IntegrationAdmin | Configure credentials/field maps and request publishing of approved versions | Cannot create scope approval through integration privileges. |
| WorkspaceAdmin | Manage memberships, project access and policies | Approval rights are explicit, not inferred from administrator status. All privileged changes are audited. |

Roles are project-scoped and may be combined. Production can require a second person for high-risk approval; the solo capstone may combine Editor/Approver with that limitation disclosed. A hosted demo allows only explicitly allowlisted accounts, not unrestricted public signup.

Stakeholder records contain display name, confirmed role, expertise areas, decision subjects, confirmation actor/time, and source references. The model may suggest a role; only authorized users confirm decision rights. Business-scope and technical-review conflicts are escalated to the configured owner, not settled by speaking time or title.

JWT validation: signature via configured issuer/JWKS, allowed algorithm, issuer, audience, expiration and subject; never accept a decoded-but-unverified token. Resolve subject to server-side membership. Supabase service-role keys and database credentials never enter React or prompts. Local seeded auth must reject startup outside local mode and must never be deployed publicly. [S8]

## 5. Frontend and user experience

| Screen | Required behavior |
| --- | --- |
| Project workspace | Current approved baseline, pending drafts/changes, source coverage, unresolved decisions and run status. |
| Source audit hub | Version list, raw normalized text/original preview, access status and exact cited paragraph/page/line. No unauthorized excerpts. |
| Backlog workspace | Expandable hierarchy, acceptance criteria, dependencies, assumption labels, citation links and human-edit markers. |
| Clarification panel | Questions with why the answer matters, source context, answer/skip, and unresolved status. Not a full chat product in the POC. |
| Change review | Side-by-side baseline/proposal; stable-ID additions/modifications/removals, affected dependencies and unsupported assumptions. |
| Approval and publishing | Version/hash confirmation, unresolved blockers, approve/reject, separate export/publish actions, per-item integration results. |
| Settings | Memberships, decision rights, source/provider policy, budgets and connector configuration. Platform phase. |

Use keyboard-accessible controls, visible labels, non-color-only status, and screen-reader announcements for progress. Target WCAG 2.2 AA practices; do not claim certification from automated scans. Markdown from sources/models must be sanitized; never render arbitrary HTML. Escape CSV cells if CSV export is later added. Use UI error boundaries, explicit retry controls and persisted run IDs. Polling is sufficient initially; SSE is an optional platform enhancement with reconnect cursors.

## 6. Data model and integrity

IDs are UUIDs; timestamps UTC. Mutable records have integer revision/ETag. Every scoped table carries workspace_id/project_id as applicable. Composite foreign keys or service checks must prevent a reference to an item in another project; a bare UUID lookup is insufficient.

| Entity | Essential fields and relationships |
| --- | --- |
| Workspace, User, Membership | Workspace policy; external auth subject; project/user/role grants. Unique membership grants. |
| Project, Stakeholder, DecisionRight | Goals, current_baseline_id; confirmed participant role/expertise; subject-to-approver assignments. |
| Document, SourceVersion | Document identity; immutable version number, checksum, media type, original_uri/text, approval/supersession status, access policy, provider-use classification. |
| SourceBlock | source_version_id, ordinal, canonical text, locator JSON (paragraph/page/line/offsets), checksum. Unique version + ordinal. |
| Statement/Requirement | Stable ID, classification, normalized meaning, topic, decision status; revised rather than silently replaced. |
| BacklogVersion | project_id, base_version_id, revision, state, content_hash, creator/run_id. Approval refers to exact immutable content. |
| BacklogItemRevision | Stable item_id plus version_id, kind, parent_item_id, title, description, criteria, human-edit flag, blockers. Unique version + item. |
| Claim, EvidenceLink | Item/criterion claim, origin (source, human, proposed), source block/version, exact quote/offset; allow multiple supporting or conflicting passages. |
| Dependency | Version, from_item, to_item, relation and rationale. Validate endpoints, self-links and blocking cycles. |
| AgentRun, RunStep | Input version IDs, status, stage, selected model/prompt version, counters, lease/version, typed result/error; durable tool-result references. |
| Clarification | Run/question ID, subject, text, answer/skip state, answering actor/time and resulting evidence block. |
| ChangeRequest, ChangeSet | Base version/hash, request evidence, proposed version; typed add/modify/remove operations and impact rationale. |
| Approval, AuditEvent | Subject/version/hash, authorized actor/role, action, time, reason; append-only business events with retention controls. |
| Connector, ExternalMapping | Encrypted secret reference, project/type/field mapping; local item ID to remote issue ID/key, last-synced values/version. |
| OutboxJob, WebhookInbox | Idempotency/dedupe key, payload reference, attempt/result state, retry time; processed remote event identifier. |

Store flexible criterion/tool payloads as schema-versioned JSON; store searchable and constrained fields relationally. Index project + state/time, source version + ordinal, run + step, and connector + external ID. Enforce uniqueness on request idempotency keys and publishing operation identities. PostgreSQL row-level security is additional defense where configured; backend checks remain mandatory and require negative authorization tests.

![Core relationships](docs/diagrams/data_relationships.svg.png)

Example item contract:

```json
{
  "item_id": "ST-004",
  "kind": "story",
  "parent_item_id": "EP-001",
  "title": "Cancel a room reservation",
  "criteria": [{
    "id": "AC-001",
    "text": "A student may cancel their own reservation before its start.",
    "origin": "human_confirmed",
    "evidence": [{"source_version_id": "SV-03", "block_id": "B-02"}]
  }],
  "open_questions": [],
  "proposed_details": [],
  "review_state": "draft"
}
```

Human-readable IDs above are illustrative; use UUIDs internally. Quote strings and locators are stored in evidence records. Splits/merges create explicit supersedes links, not deceptive reuse of an unrelated stable ID.

## 7. Ingestion, retrieval, and provenance

Pipeline: authorize intake → validate/quarantine → immutable original/version → normalize into stable blocks → classify access/provider eligibility → index → retrieve → attach evidence. POC accepts UTF-8 TXT/Markdown only: two initial files, maximum 512 KiB each and 6,000 words combined. These are proposed application limits, not provider limits.

Platform parsers add PDF text extraction, then OCR only with a quality warning and visual/page evidence. Reject unsupported types, oversized/zip-bomb inputs, active content and unreadable documents. Scan/quarantine untrusted binary uploads before parsing in isolated workers. Uploaded filenames are display metadata, never server paths.

Wiki/repository connectors are read-only initially. Use installation/project-scoped credentials, pagination, content hashes and incremental refresh. Block internal-network/metadata URLs and redirects to disallowed destinations when fetching user links. Pin repository evidence to commit SHA plus file/line range; exclude secrets, binaries, vendored/generated trees and unsupported file types. Do not execute ingested repositories in the POC.

POC uses authorized paragraph lookup and full small-document context. Platform starts with metadata + lexical search; add embeddings/hybrid retrieval only when recall tests show a benefit. Store embedding model/version and invalidate derived vectors on deletion or permissions changes. Apply ACL filters before retrieval and recheck every returned citation. Do not retrieve all tenants and redact afterward.

Derived drafts, answers and reports inherit the intersection of access permissions for all source context used, not just the passages eventually cited. Approval does not declassify restricted information. Broader sharing requires a separately authorized, recorded release/redaction decision. Jira publishing must verify that the destination audience is allowed to receive the proposed content; hiding citation links alone does not prevent leakage.

Source precedence is explicit: an approved baseline persists until authorized change. A newer meeting, senior-sounding speaker, or an unapproved upload does not override it. Store contradicted passages and ask the assigned decision owner. Corrections create new source versions; original citations remain historically stable but are labeled superseded. Access revocation hides historical excerpts too.

Deletion policy: immediately revoke visibility, then purge originals, blocks, indexes, generated excerpts and cached prompts within a documented processing window. Retain only permitted minimal audit metadata. Backup retention can delay physical erasure and must be disclosed. Synthetic capstone datasets may be retained for evaluation; real data requires an approved retention/provider policy first.

![Ingestion and evidence flow](docs/diagrams/ingestion_flow.svg.png)

## 8. AI engine and agent harness

A harness is the application runtime around the model: context assembly, tool execution, state, validation, approvals, budgets and telemetry. It is not training a foundation model. FastAPI serves the product API; it is not, by itself, an agent runtime.

| Approach | Assessment and decision |
| --- | --- |
| Direct SDK + typed bounded loop | POC default. Transparent behavior, minimal dependencies; team owns persisted state, pause/resume and retry correctness. Keep provider operations behind one interface. |
| LangGraph | Preferred platform candidate when branching and durable human interrupts are needed. Persistent checkpointer required; framework does not replace authorization, business versioning or remote-write reconciliation. [S1] |
| Provider agent SDK | Useful if the team commits to one ecosystem. Evaluate tracing, structured output and portability before adoption; not required for the POC. |
| LangChain/LlamaIndex retrieval abstractions | Optional for complex connectors/retrieval. Do not add both merely to claim RAG; evaluate against direct retrieval first. |
| Multi-agent design | Deferred. Separate prompts/validators can provide role-specific checks without autonomous agents negotiating authority. |

Provider interface: `generate(messages, tools, output_schema, limits) -> ProviderResult`. Result includes typed tool requests or candidate output, finish reason, usage, provider/model/version, and error classification. Configure capabilities explicitly: tool calling, structured output, context/output size and privacy terms. An OpenAI-compatible endpoint is not proof of identical schema support.

Harness context: project policy, actor's permitted tools, pinned source IDs, approved baseline, unresolved decisions and confirmed answers. No cross-project memory. Organizational memory stores only approved, attributable records with retention/access rules; do not treat old model summaries as authority.

POC tool contracts:

| Tool | Input and result |
| --- | --- |
| lookup_source | Authorized project/source version IDs, query/block IDs and bounded limit → block IDs, text, locators, classification. Read-only. |
| request_clarification | Subject, question, relevant evidence, affected item IDs → saved question ID and WAITING_FOR_INPUT state. |
| validate_backlog | Typed candidate + pinned source/baseline IDs → schema/reference/dependency/blocker errors and warnings. |

Draft/change generation uses structured model output, not a privileged write tool. Domain services persist candidate revisions. Approval/export/publish are separate authenticated API operations; never expose them as autonomous tools. Add technical-repository tools later under read-only permissions.

Run record persists statuses `created`, `running`, `waiting_for_input`, `ready_for_review`, `failed`, `cancelled`. Processing stages include retrieve, reason/tool-selection, draft and validate. Set initial caps: six model turns, eight tool calls, two clarification rounds per run, one schema-repair attempt, and a configurable per-run output-token limit. Resume does not reset counters. Limits are proposed defaults to tune using evaluation.

Execution: acquire a short run lease → load snapshot → call model/tool outside database transaction → validate → commit using run revision → release lease. POC advances one bounded step per request; browser polling can request the next step. A closed browser pauses progress but must not lose state. Expired leases permit retry; lost inference responses may incur duplicate billing and must be disclosed, not reported as exactly-once execution. Duplicate draft commits are prevented by step identity/version checks. No uncontrolled background loop on a sleeping free host.

Platform workers use database-backed jobs/outbox, attempt identities and durable checkpoints. A queue acknowledgment is not a business commit. Failed/stalled runs have an operator-visible recovery path. Use bounded exponential backoff with jitter for transient network/429/5xx errors, respect Retry-After and budgets; do not retry permission or schema errors indefinitely.

![Agent execution](docs/diagrams/agent_execution.svg.png)

## 9. Output validation and source trust

Validation layers: provider structured output → Pydantic → domain invariants → evidence-reference/quote checks → human semantic review. Check IDs, parents, scope classification, allowed operations, dependencies, duplicate candidates, approval blockers and changed-source access. Model-generated valid JSON is not automatically a valid plan.

Acceptance criteria inferred by AI are marked proposed until reviewed. User edits preserve origin and invalidate affected approvals. Unresolved conflict on an item blocks its approval; unrelated resolved work can form a separately reviewed partial baseline. Confidence labels describe evidence status (supported/conflicting/missing), not invented probability scores.

Uploaded instructions are data, not system policy. Tool policies are enforced in code; do not trust prompts to prevent publishing or cross-project access. Treat tool output as untrusted content. Never send credentials, full logs or unrestricted source collections to a model. Record observable tool requests/results, not private chain-of-thought. Security guidance: [S2].

## 10. Approval, changes, and planning

Candidate versions progress `draft -> in_review -> approved` or `rejected`; editing an in-review candidate returns it to draft. Approval binds actor, role, source/baseline versions, candidate revision and content hash. Application policy verifies all blockers and an optional separation-of-duties rule.

Change requests are interpreted against the pinned approved version. Operations: add item, modify fields/criteria, remove item, or change dependency. Show a semantic diff plus before/after values. Preserve untouched IDs and content. An unexpected full rewrite is rejected or explicitly escalated. A concurrent baseline update yields HTTP 409; rebase and review again. Historical approved versions remain immutable; restoration creates a new approved version, not an audit-history rewrite.

Scope impact includes affected stories, dependencies, conflicting decisions, unknown effort and needed reviewer input. Later forecasts require effort ranges, team capacity/calendar, dependencies and historical calibration. ROI scenarios require supplied rates/costs and benefit assumptions; show ranges and sensitivity, never a claim of causation or guaranteed savings. Repository-derived suggestions remain unverified until tests/reviewer sign-off.

![Scope change lifecycle](docs/diagrams/scope_change_lifecycle.svg.png)

## 11. API contracts and application errors

Prefix `/api/v1`. JSON request/response schemas are versioned. Resolve workspace/project through membership on every route. Return ETag/revision on mutable resources. Use `If-Match`/expected revision for edits and approval. Mutating commands accept Idempotency-Key scoped to actor/project/action; same key + different payload returns conflict. No inference API key reaches the browser.

| Endpoint | Contract and policy |
| --- | --- |
| POST /projects; GET /projects/{id} | Create/access project; platform membership checks. POC may seed one project. |
| POST /projects/{id}/sources | Multipart upload; 201 source/version IDs and parse status. Limits/media/auth enforced before ingestion. |
| GET /projects/{id}/sources/{version}/blocks | Authorized block list/lookup; no direct public object URLs. |
| POST /projects/{id}/runs | Mode initial/change, pinned source IDs, base version if change, request text; 202 run ID/status. |
| POST /runs/{id}/advance | POC bounded next step; lease and idempotency required. Platform worker replaces browser-driven advancement. |
| GET /runs/{id}; POST /runs/{id}/cancel | Status, counters, redacted events, questions, result revision; cooperative cancellation. |
| POST /runs/{id}/answers | Question ID + answer/skip; actor recorded; resumes without resetting run budget. |
| GET /projects/{id}/backlogs/{version} | Items, criteria, evidence, dependencies, revision, blockers and diff metadata. |
| PATCH /backlogs/{version}/items/{item} | Allowed draft-field patch + expected revision; preserves stable ID, labels human edits. |
| POST /backlogs/{version}/review | Validate and enter review; returns blocking issues, not silent model fixes. |
| POST /backlogs/{version}/approve or /reject | Approver + exact revision/hash + expected current baseline; atomic transaction and audit event. |
| GET /backlogs/{version}/export?format=json | Approved version only; Markdown also supported. Recheck permission for evidence included in export. |
| POST /backlogs/{version}/publish | Platform/POC stretch: approved revision + connector + explicit confirmation; 202 job; IntegrationAdmin privilege. |
| GET /publish-jobs/{id}; POST /connectors/jira/webhook | Per-item results; later authenticated/deduplicated event ingestion. |

Example create-run request: `{"mode":"change","base_version_id":"UUID","source_version_ids":["UUID"],"request_text":"Add recurring reservations"}`. Response: `{"run_id":"UUID","status":"created","revision":1,"next_action":"advance"}`.

Error body: `{"code":"BASELINE_CONFLICT","message":"Review the newer baseline","request_id":"UUID","retryable":false,"details":{"current_version_id":"UUID"}}`. Use 400 invalid command, 401 unauthenticated, 403 unauthorized, 404 absent/inaccessible object where appropriate, 409 stale/idempotency conflict, 413 oversized, 415 unsupported media, 422 invalid schema/domain input, 429 quota, and 503 provider unavailable. Never include secrets or private source excerpts in generic errors.

## 12. Jira and external integrations

Default Jira hierarchy: Epic -> Story/Task/Bug -> Subtask. Initiatives/additional levels depend on plan and configuration. Never change an existing Jira hierarchy to accommodate ScopeSteps. Discover create metadata and required fields; Jira v3 description fields use Atlassian Document Format. [S3][S4]

One-way publisher: verify approved version/access → create unique outbox job → discover schema → create parents before children → store external keys and per-item outcomes → reconcile ambiguous results. Idempotency identity includes connector/project/local item/approved revision/operation. Persist mappings before reporting success. A remote POST timing out is not evidence that no issue was created; inspect correlated remote state or mark needs_attention instead of blind retry. Do not promise exactly-once effects from an API lacking that guarantee.

POC optional connector uses a dedicated sandbox account with scoped project permissions and server-side token storage. Platform uses installation/OAuth grants as applicable; revalidate scopes, refresh/rotate securely, disconnect/revoke cleanly. Connector secrets are encrypted via a secret manager, never stored in model-visible state.

Later two-way sync uses a webhook inbox with provider-specific authenticity checks, replay protection and durable deduplication. If the selected Jira webhook mode lacks signed payloads, do not invent HMAC guarantees: use authenticated registration/ingress where available and treat events as hints, fetching authorized current issue state. Jira supplies a retry-stable webhook identifier. [S5]

Field ownership default: Jira owns execution status/assignee; ScopeSteps proposes scope/title/criteria changes; shared fields require three-way comparison against last-synced values and human conflict review. Track origin/version to prevent echo loops. Out-of-order events fetch latest state; permission loss and deleted issues become visible exceptions, not recreated issues or automatic deletions. Integration changes never bypass baseline approval.

![Jira synchronization](docs/diagrams/jira_sync.svg.png)

## 13. AI provider selection and free inference

Free chatbot access is not free application API access. OpenAPI is an interface specification, not a model provider. OpenRouter is a gateway. Self-hosting an open model has hardware/hosting costs even when no API token fee applies.

| Option | Cost/access and decision |
| --- | --- |
| Gemini Developer API | Genuine model-dependent free tier with quotas. Pricing page indicates free-tier data may be used to improve products; capstone uses synthetic data only. Recommended first candidate, not a final quality endorsement. [S9] |
| OpenRouter free variants | Only catalog entries offering a free variant qualify. Limits, availability, tool support and downstream provider terms vary. Pin model/provider routing where supported; check current capabilities instead of using random routing. [S10][S11] |
| Ollama local inference | No hosted inference charges when running a local model; needs adequate RAM/compute and an appropriate model license. Validate tool calling, latency and context size. Not deployable on a tiny free backend by assumption. [S12] |
| Claude API | Metered model/tool pricing; do not assume a free Claude chat account supplies API credits. Strong paid fallback candidate only after budget/privacy approval. [S13] |
| OpenAI API | Metered model/tool pricing; no assumed ongoing free allowance. Choose an API model by evaluation, not consumer ChatGPT access. [S14] |
| Kimi API | Official documentation describes pay-as-you-go inference separate from membership/code products. Do not assume free file extraction makes inference free. [S15] |

Model-selection spike: run identical fixtures through the candidate; verify structured output, tool arguments, citations, clarification, provider errors, usage reporting and schema repair. Record exact model ID, configuration, prompt/schema versions, results and account quota. Do not pin an untested model ID in this proposal. Ship one provider initially behind an adapter. Switching requires an approved data-policy-compatible alternative and is logged; no silent fallback that sends data to another company.

Cost estimate formula: sum across every call `(input_tokens × input_rate + output_tokens × output_rate) / 1,000,000`, plus tools, caching/storage and provider-specific charges. Include retries, repeated context, and billed reasoning tokens where applicable. Record measured p50/p95 tokens and cost per completed scenario. Free quota is a usage ceiling, not infinite throughput. Enforce application run/project budgets before each call; paid access is opt-in and fallback never silently upgrades billing. Do not claim a guaranteed currency cap when providers meter delayed or partially unreported usage.

## 14. Environments, configuration, and secrets

| Environment | Configuration and policy |
| --- | --- |
| Local development | React dev server + FastAPI bound to loopback; SQLite or local Postgres. Seeded local actor, synthetic fixtures, optional real API key. Git-ignored .env with placeholder .env.example. |
| CI/test | Temporary database, mocked provider/connector adapters, no production secrets. Optional separately approved live smoke tests with strict quota. |
| Staging/demo | Deployed React + FastAPI, persistent external Postgres, hosted JWT auth + user allowlist, synthetic-only sources. Separate keys/project from production. |
| Production | Separate accounts/projects, least privilege, approved provider/privacy policy, durable workers, backups/restore tests and reviewed alerts. Not a free-tier reliability claim. |

Configuration contract: `APP_ENV`, `DATABASE_URL`, `AUTH_MODE`, `AUTH_ISSUER`, `AUTH_AUDIENCE`, `AUTH_JWKS_URL`, `CORS_ALLOWED_ORIGINS`, `MODEL_PROVIDER`, `MODEL_ID`, provider-specific secret key, `RUN_MAX_TURNS`, `RUN_MAX_TOOLS`, `RUN_MAX_OUTPUT_TOKENS`, `RUN_COST_LIMIT`, `PROJECT_COST_LIMIT`, `SOURCE_MAX_BYTES`, `SOURCE_MAX_WORDS`, `OBJECT_STORE_*`, and later `QUEUE_URL`/connector secret references. Defaults and validation are documented in application settings; refuse unsafe production defaults.

Never prefix secrets with VITE_; only API base URL and intended public auth configuration enter the browser bundle. Set exact CORS origins and HTTPS; CORS is not authentication. Use the auth SDK with a documented token/session strategy, short access-token lifetime, no tokens in logs/URLs, CSP and no unsafe HTML. If cookies are used, implement Secure/HttpOnly/SameSite and CSRF protection as appropriate. Review the selected strategy before production.

## 15. Deployment paths and free-tier limits

| Component | Capstone recommendation | Constraints / migration |
| --- | --- | --- |
| React hosting | Cloudflare Pages Free | Static build, preview URLs and documented build/asset quotas. FastAPI runs elsewhere; configure SPA fallback and public API origin. [S16] |
| FastAPI hosting | Render Free, optional | Spins down after 15 minutes without inbound traffic; restart can be slow. Local files are ephemeral; no SQLite/uploads there as durable storage. Do not rely on continuous worker/scheduler execution. [S17] |
| Postgres + auth + files | Supabase Free | Current listed limits include 500 MB database, 1 GB file storage, two active projects; free projects may pause after a week of inactivity. Verify quotas/connectivity at deployment. [S18] |
| Zero hosted inference charge alternative | Local Ollama + local app | Hardware-dependent. Keep local development available as the demo fallback; it is not a cloud availability solution. |
| Paid core platform | Container API + durable workers + managed Postgres/object storage | Budget for always-on execution, backups, logs and connector traffic. Keep source/storage/provider adapters portable. |

Recommended demo deployment sequence: create isolated demo auth/database → run reviewed Alembic migration → seed allowlisted membership → set backend secrets/origins → deploy API with health checks → deploy static React using public API URL → verify login, source access, persistence and restart recovery → exercise full demo → export local backup before presentation. Supabase DB connection method/pooling must match the host's network support; migration tooling may require a different connection than application pooling. Rehearse the cold start; do not promise a permanently awake free backend.

Render's free Postgres expires after 30 days, so it is not the recommended proposal archive. Keep database/text outside Render's ephemeral disk. POC steps persist before/after calls and can resume after a lost request; free hosting remains unsuitable for dependable unattended long jobs. [S17]

### AWS alternative

A conventional later AWS layout: private S3 + CloudFront for static React, ECS/Fargate API and worker containers, load balancer, RDS PostgreSQL, private S3 documents, Redis-compatible queue service, Secrets Manager and CloudWatch. Use OIDC-based CI deployments and narrowly scoped task roles. Do not introduce EKS/Kubernetes for this project. Network layout, outbound provider access, backup policy and regional requirements need a separate costed deployment review.

AWS currently advertises up to $200 in new-customer credits: $100 initially and up to $100 earned; Free plan ends after six months or credit exhaustion and has service restrictions. Account eligibility, service coverage, and paid-plan transitions must be checked. The architecture above is not guaranteed to be covered. [S19]

Paid AWS costs can include load balancers, NAT/egress, public IPv4, RDS, queue/cache, secrets and logs even with little application traffic. Create tags/budgets/alerts, documented teardown and least-privilege accounts before provisioning. AWS Budget notifications are delayed and are not a hard spending cap. Do not assume Bedrock or third-party model inference is free with general credits. [S20]

## 16. CI/CD, migrations, and recovery

Pull request checks: frontend lint/typecheck/unit tests, Python lint/typecheck/unit tests, API schema compatibility, database integration tests, permission tests, dependency/security checks, secret scan and a Playwright critical-flow test. Lock dependencies; cache builds, not credentials. Provider responses and external services are mocked in routine CI.

Deployment: build versioned artifacts → apply reviewed backward-compatible migration → deploy staging → smoke test → manually approve production → deploy immutable image/build → monitor. Use expand/contract migrations; back up before destructive changes. Application rollback must remain compatible with the current database schema. Do not automatically roll back a migration by dropping newly written user data.

Health endpoints: `/health/live` checks process; `/health/ready` checks required database/schema without running billable model calls. Expose worker heartbeat and oldest queued job. Core platform initial goals: non-AI p95 reads below one second for defined small test load; durable state across process restart; proposed production RPO 24 hours and RTO four hours, conditional on funded backups and a demonstrated restore test. These are design targets, not a free-tier SLA.

Store schema versions and export backups; test restore into an isolated environment. Planned retention defaults for a synthetic capstone: 30 days for redacted run telemetry, project lifetime for approved artifacts, and review before deleting evaluation data. Real customer policy supersedes these defaults and requires explicit agreement. Backup deletion lag must be disclosed.

## 17. Security, observability, and failure handling

Threats: unauthorized cross-project retrieval, insecure direct object references, prompt injection, malicious documents/links, credential leakage, XSS in model output, forged/replayed integration events, duplicate side effects, runaway inference and unsupported scope commitments. Controls are enforced outside the model and verified with adversarial tests.

Audit events record actor, project, action, affected version/hash, outcome and timestamp. Operational traces record request/run/step IDs, durations, provider/model, token usage, retry/error category and tool names. Default logs exclude document bodies, secrets and raw prompts. Optional diagnostic capture is restricted, consented and short-lived.

Monitor failed/paused runs, exhausted quotas, validation failures, citation failures, queue age, integration conflicts, token usage and cost per scenario. Alerts must distinguish provider outage from user permission/configuration issues. Invalid API keys require operator action, not repeated retries. Cancellation stops new steps; in-flight provider calls may still bill.

A provider outage leaves a recoverable run and clear UI message. A source permission change rechecks pending runs before the next retrieval/model call. A stale baseline blocks approval. An uncertain Jira write is needs_attention. A revoked connector stops new writes and retains the minimal authorized audit trail. Deletion of sensitive data triggers cache/index/derived-output review.

## 18. Evaluation and definition of readiness

Use a manually annotated, synthetic benchmark with fixed sources and expected decisions. Include clean requirements, rejected features, contradictions, missing information, amendments, duplicate requests, stale baselines, prompt-injection text and inaccessible sources. Keep development and held-out packs separate. Evaluate semantic requirements, not exact ticket count or wording.

Baseline: single-pass model with the same initial documents/model configuration. Report that the agent may obtain new clarification evidence; include a second comparison supplying those final answers to the baseline to separate the value of new information from orchestration. Record human edits and adjudicate ambiguous labels.

Metrics: requirement coverage; unsupported commitment rate; citation support accuracy; conflict/clarification handling; correct changed-item set; unintended alteration of unchanged approved work; correction count/time; latency, model/tool calls and token cost. Human rubric checks testability of acceptance criteria and correct distinction between sourced and proposed details. Small sample results are illustrative, not proof of market-wide effectiveness.

POC acceptance: all required flows pass, no unauthorized/automatic approval, original baseline preserved, references valid, failures visible; numerical model-quality results reported honestly. Platform release additionally needs source-access revocation tests, queue/retry recovery, connector reconciliation, backup restore, authenticated deployment and agreed privacy terms. Do not claim production readiness from a successful capstone demo.

## 19. Delivery phases and unresolved decisions

| Phase | Scope and exit condition |
| --- | --- |
| P0: one-week POC | React/FastAPI/Python; two small text sources; clarification; cited epics/stories; approved baseline; one change diff; approved export; evaluation. See companion plan. |
| P1: core platform | Hosted identity and permissions, Postgres/object storage, richer review UI, durable jobs, source/version lifecycle and approved one-way Jira publishing. |
| P2: expanded intelligence | Wiki/repository/PDF ingestion, evaluated hybrid retrieval, confirmed stakeholder profiles, technical-review evidence and explicit planning scenarios. |
| P3: integration hardening | Conflict-aware two-way sync, operational recovery, privacy/compliance review, calibrated estimates and broader user evaluation. |

Before implementation, confirm team ownership, rubric, allowed cloud accounts/region, public-demo requirement, synthetic-data policy, Jira plan/project/permissions, exact model ID/account quotas, spending cap and reviewer availability. Proposed defaults are recorded here; unresolved details are not permission to silently expand scope. No guaranteed task durations or business ROI are asserted.

## 20. Sources and document maintenance

Official documentation validates available capabilities/constraints, not the proposed product's accuracy or business demand. Vendor terms change; store date and chosen account/model settings with evaluation evidence.

- S1: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) and [persistence/durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution).
- S2: [OpenAI agent safety](https://developers.openai.com/api/docs/guides/agent-builder-safety).
- S3: [Jira hierarchy](https://support.atlassian.com/jira-cloud-administration/docs/configure-the-issue-type-hierarchy/) and [work types](https://support.atlassian.com/jira-cloud-administration/docs/what-are-issue-types/).
- S4: [Jira issue APIs and create metadata](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/).
- S5: [Jira webhooks and retry identifiers](https://developer.atlassian.com/cloud/jira/platform/webhooks/).
- S6: [Anthropic: building effective agents](https://www.anthropic.com/engineering/building-effective-agents).
- S7: [FastAPI background-task limits](https://fastapi.tiangolo.com/tutorial/background-tasks/).
- S8: [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts).
- S9: [Gemini API pricing/data-use terms](https://ai.google.dev/gemini-api/docs/pricing) and [function calling](https://ai.google.dev/gemini-api/docs/function-calling).
- S10: [OpenRouter free variants](https://openrouter.ai/docs/guides/routing/model-variants/free).
- S11: [OpenRouter model capabilities API](https://openrouter.ai/docs/api-reference/models/get-models).
- S12: [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling).
- S13: [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing).
- S14: [OpenAI API pricing](https://developers.openai.com/api/docs/pricing).
- S15: [Kimi API pricing](https://platform.kimi.ai/docs/pricing/chat).
- S16: [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/).
- S17: [Render Free limitations](https://render.com/docs/free).
- S18: [Supabase pricing and free quotas](https://supabase.com/pricing).
- S19: [AWS Free Tier](https://aws.amazon.com/free/).
- S20: [AWS Budgets and notification delays](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).
- S21: [APM change-control guidance](https://www.apm.org.uk/resources/what-is-project-management/what-is-change-control/).

Document sources: project proposal Markdown under `docs/source/`; POC Markdown at repository root is authoritative for its Word version. Diagrams have editable `.mmd` and `.svg` sources plus `.svg.png` previews under `docs/diagrams/`. Regenerate diagrams with `python3 docs/diagrams/build_diagrams.py`; on macOS render previews with `swift -module-cache-path docs/build/swift-cache docs/diagrams/render_diagrams.swift docs/diagrams/*.svg`. Build both Word documents with `python3 docs/build_documents.py`. This dependency-free document builder is documentation tooling, not application code. Validation output is `docs/build/validation_report.json`; the original proposal checksum is preserved there alongside extracted text.

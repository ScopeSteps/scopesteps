# Product overview

ScopeSteps helps product owners and project leads turn meeting transcripts, project documents
and (later) repository and wiki knowledge into reviewable scope and structured backlogs.

## Users

- **Primary:** product owner or project lead preparing scope and coordinating approval.
- **Supporting:** stakeholders (business context), engineers (technical review), approvers
  (decision owners), integration administrators, read-only reviewers.

Expertise, administrative access and authority to approve scope are separate concepts.

## Core workflow

1. Upload or connect sources; ScopeSteps versions them into stable, citable blocks.
2. The agent separates decisions, suggestions, exclusions and unknowns, and asks targeted
   clarification questions. Answers become attributed evidence.
3. Users review a draft backlog (epics, stories, acceptance criteria) where every claim links to
   the passage that supports it, or is labelled as AI-proposed.
4. An authorized approver approves an exact version. It becomes an immutable **baseline**.
5. New requests produce a **candidate change** (a diff against the baseline), never a silent edit.
   Approval creates a new baseline; rejection leaves the old one untouched.
6. Approved versions can be exported, and later published to Jira.

## Product invariants

- Discussion is not commitment.
- The model proposes; application policy decides. No model tool can approve, publish or change
  permissions.
- Approved versions are immutable.
- Evidence points to a specific source version and location.
- Project isolation applies everywhere: retrieval, citations, runs, exports, integrations.
- No requirement is invented to fill a quota; insufficient input produces an explicit unknown.

## Out of scope

ScopeSteps does not inherit anyone's organizational authority, train a foundation model, or
guarantee forecasts. Estimates (phase P2) are only produced from explicit inputs.

Source: [Project Proposal](../proposals/ScopeSteps%20Project%20Proposal.docx).

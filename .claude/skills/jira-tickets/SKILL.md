---
name: jira-tickets
description: How ScopeSteps work is planned and tracked in Jira (project SSPOC). Use when writing, splitting, linking, reordering or closing a ticket, when checking what to work on next, or when a pull request changes a ticket's status.
---

# Jira tickets in ScopeSteps

All POC work lives under epic SSPOC-1 at https://scopesteps.atlassian.net (team-managed project
SSPOC). Jira and the repo must agree: the build-order comment on SSPOC-1, the "blocks" links and
`docs/status/roadmap.md` describe the same plan.

Changing Jira is visible to the team: create, edit, link or move tickets only when asked.

## Access

- The `jira` CLI reads and writes; set it up with `jira init` and your own API token in
  `JIRA_API_TOKEN`. Never commit, print or paste a token, and never put one in a script in the
  repo.
- Useful reads: `jira issue view SSPOC-12`, `jira issue list -q 'parent = SSPOC-11'`,
  `jira issue list -q 'statusCategory != Done' --plain`.
- When a write is blocked for an agent, write the command or script and ask the person to run
  it.

## Ticket shapes

| Type    | Use for                                 | Parent    | Criteria live in                |
| ------- | --------------------------------------- | --------- | ------------------------------- |
| Story   | Something a user can do                 | SSPOC-1   | the "Acceptance Criteria" field |
| Task    | Work with no user-facing behaviour      | SSPOC-1   | the "Acceptance Criteria" field |
| Subtask | The backend or frontend half of a story | the story | the description                 |

- A story gets one backend subtask (`BE — …`) and one frontend subtask (`FE — …`). Skip one
  only when that half has no work.
- Titles say what the ticket delivers, in plain words: "Create, switch and rename projects".
- Do not set sprints, due dates or effort estimates. Order comes from the build order.

## Description template

Stories and tasks:

1. A user-story line: "As a <role>, I want <capability> so <outcome>."
2. Context: what exists today, what changes, and any dated decision ("Decided 2026-10-13
   (Sara): …"). Name the decisions that need an ADR or a roadmap change.
3. Design reference, for UI work: the prototype screen, and that demo features are not built
   (see the `design-system` skill).
4. **Implementation checkpoint:** "Sequence only; the agreed order is in the comment on SSPOC-1.
   No sprint, due date or effort estimate."
5. **Dependencies:** the tickets that block this one, or "None".
6. **Definition of Done**, word for word:
   - Acceptance criteria demonstrated with synthetic data and relevant automated tests or
     recorded verification evidence.
   - No credentials in client bundles, source control, logs, or model-visible context.
   - Changes preserve source provenance, human approval boundaries, and existing approved
     versions.
   - Implementation matches the documented React/FastAPI/Python POC contracts; unresolved
     deviations are recorded.
   - just check passes and the docs named in AGENTS.md "Definition of done" are updated in the
     same pull request.

Subtasks use the same sections, with an **Acceptance criteria** section in the description
after the context.

## Acceptance criteria

- Each criterion is one observable result a reviewer can check: "Sign-out invalidates the
  session on the server", not "Implement sign-out properly".
- Cover the unhappy paths: wrong role, stale revision (409), missing data, limits.
- Name the contract, migration, tests and docs the change must update.
- For agent work, say that live measurement happens only after asking.

## Dependencies

- Link with "blocks". Link the subtasks that really depend on each other (BE → FE, one
  backend change → the next); a story is blocked when one of its subtasks is.
- `jira issue link A B Blocks` records "A blocks B". Jira's REST API names the two sides the
  other way round, so check the result with `jira issue view` after linking.
- After adding or removing a link, update the build-order comment on SSPOC-1 and the
  "P0 build order" section of `docs/status/roadmap.md` in the same change.

## Build order

- One row per story or task, with its subtasks, what it waits on (backend and frontend
  separately) and what it unblocks. Rows with the same stage can run in parallel.
- A ticket's stage is one more than the highest stage it waits on. Backend subtasks with no
  blockers can start before their stage; list them under "Can start today".
- Call out the bottlenecks (tickets that block many others) and anything that changes the agent,
  since those merge one at a time.

## Status

- Move a ticket to In Progress when its branch is opened and to Done when its pull request is
  merged and its criteria are shown working.
- Put the key in the branch or pull request summary (`SSPOC-12`) so the history links up.
- Close a story when both subtasks are Done. Do not leave an open subtask under a Done parent;
  move it to its own task or finish it.
- The pull request that changes a status also updates `docs/status/roadmap.md` (AGENTS.md
  "Definition of done").

## Checklist for a new ticket

- Right type and parent, with a BE and FE subtask for a story?
- User-story line, context, design reference, checkpoint, dependencies and the five-line
  Definition of Done?
- Every criterion observable, unhappy paths included?
- "Blocks" links added and checked, and the build order and roadmap updated?

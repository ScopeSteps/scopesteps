---
name: pull-request
description: How to open, update and review pull requests and follow GitHub practice in ScopeSteps. Use when asked to push a branch, open or edit a PR, write a PR title or description, respond to review comments, review someone's PR, or check CI.
---

# Pull requests and GitHub practice in ScopeSteps

Pushing and opening a PR are visible to the team: do them only when asked. Commits follow the
`commit` skill. GitHub operations use the `gh` CLI.

## Branches

- Branch from an up-to-date `main`: `<type>/<short-description>` (`feat/source-upload`).
- One branch, one purpose. Keep it short-lived and update it from `main` if it falls behind.
- `main` is protected in practice: no direct pushes, no force-pushes, changes arrive by PR.

## Before opening

1. `just check` passes locally. CI runs the same checks.
2. `git log main..HEAD` and `git diff main...HEAD` to read the whole change as a reviewer will.
3. The diff contains only this change: no stray files, debug output, secrets or real data.
4. Docs changed with the code: README, the relevant `docs/` page, the roadmap status, an ADR
   for a significant decision.

## Size

Aim for a PR a reviewer can read in one sitting. If a change is large, split it: a refactor
that changes no behaviour first, then the feature. Contract, schema and behaviour changes are
easier to review apart.

## Title

PRs are squash-merged, so the title becomes the commit on `main`. Write it as a Conventional
Commit, same rules as the `commit` skill: `feat(agent): add clarification loop with skip`.

## Description

Fill in [.github/pull_request_template.md](../../../.github/pull_request_template.md); keep
every heading.

- **Summary:** what the PR does and why, in two or three sentences. Lead with the outcome, link
  the issue or ticket.
- **Changes:** a short list of the notable changes, grouped by module. Not a file list.
- **Testing:** the commands you ran and their result, tests added, and manual checks. Say
  plainly what was not tested. For UI changes add a screenshot.
- **Breaking changes:** API contract, database schema or configuration changes that break
  existing behaviour, with what a teammate must do after pulling. `None` if none.

For harness or prompt changes include the before and after eval numbers with their intervals.

Open it with `gh pr create --title "…" --body-file <file>`; use `--draft` while work is unfinished.

## After opening

- Watch CI (`gh pr checks`). A red check is yours to fix; do not ask for review on a red PR.
- Reply to every review comment: fix it, or explain why not. Push follow-up commits instead of
  force-pushing during review, so reviewers can see what changed.
- Resolve a thread only when its point is addressed. Let the reviewer resolve disputed ones.
- Do not merge your own PR without the review the team expects, and never merge with failing
  checks.

## Reviewing someone else's PR

- Read the description, then the whole diff, then run it if behaviour changed.
- Check, in this order: is it correct, does it respect module boundaries and layers, is it
  tested, is the contract or migration regenerated, is it readable.
- Say which comments block merging and which are suggestions. Be specific and propose the fix.
- Approve when it is good enough to merge, not when it is how you would have written it.

## General GitHub hygiene

- Never commit secrets. If one is pushed, treat it as leaked: rotate it first, then remove it.
- Keep issues and PRs linked so the history explains itself.
- Dependency updates from Dependabot get the same checks as any PR; read the changelog for
  major versions.
- Do not edit workflow files in `.github/workflows/` as a side effect of another change.

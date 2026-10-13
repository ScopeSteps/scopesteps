---
name: commit
description: How to make git commits in ScopeSteps. Use whenever asked to commit, stage, amend or split changes, or to write a commit message.
---

# Committing in ScopeSteps

Commit only when asked. Rules come from [CONTRIBUTING.md](../../../CONTRIBUTING.md); commitlint
checks the message in the commit-msg hook.

## Before committing

1. `git status` and `git diff` (and `git diff --staged`) to see exactly what would go in.
2. Never commit on `main`. Create a branch first: `<type>/<short-description>`, for example
   `feat/source-upload`.
3. Run `just check`. If something fails, fix it or tell the user; do not commit around it.
4. If an endpoint or schema changed, `just contract` and include the regenerated files. If a
   model changed, include its migration.

## What goes in one commit

- One logical change that passes the checks on its own. Split unrelated work into separate
  commits, and keep a pure rename or reformat apart from a behaviour change.
- Tests and docs travel with the code they describe, including `docs/status/roadmap.md` when a
  status changes.
- Stage files by name. Avoid `git add -A` and `git add .`, which pick up stray files.
- Never commit `.env`, credentials, real documents, `evals/reports/`, local databases or other
  generated output. Look at the staged list for anything unexpected.

## The message

One line, [Conventional Commits](https://www.conventionalcommits.org/):

```text
type(scope): summary
```

- **type:** `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, `chore`, `revert`.
- **scope:** the module or app the change belongs to: `agent`, `sources`, `backlog`, `evidence`,
  `change_control`, `projects`, `identity`, `api`, `web`, `evals`. Omit it only when the change
  is truly repo-wide.
- **summary:** imperative mood, lower-case start, no full stop, under about 72 characters. Say
  what changes for someone reading the log, not which files were touched.
- A breaking change gets `!` after the scope and is called out in the pull request.

```text
feat(sources): validate upload size before splitting blocks
fix(agent): count timed-out model calls against the run budget
docs: record free-tier limits and first single-pass baseline
```

Not `update files`, `fix bug`, `WIP`, or a summary that lists two unrelated things; that last
one means the commit should be split.

Trailers such as `Co-Authored-By:` go after a blank line and do not break the one-line rule.

## Hooks and history

- The pre-commit hook formats staged files and re-stages them. If a hook fails, fix the cause
  and commit again. Never pass `--no-verify`.
- Do not amend, rebase or force-push commits that are already pushed unless the user asks. On a
  shared branch use `--force-with-lease`, never a plain force.
- Never rewrite `main`.

After committing, show the resulting `git log --oneline` line and `git status`.

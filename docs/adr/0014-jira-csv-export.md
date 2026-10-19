# 0014. Approved backlogs export as a Jira CSV; Markdown export is removed

- Status: Accepted
- Date: 2026-10-19

## Context

The [POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md) asks for
"approved JSON/Markdown exports", and `GET /backlogs/{version}/export` delivered both, with the
Export modal offering each. Neither moves a backlog into a tracker: a team copies every epic and
story into Jira by hand. Publishing straight to Jira is a stretch item that needs credentials and
field discovery, and the plan keeps file export as its fallback.

Jira Cloud's CSV importer already creates linked work items from a file. Its documented hierarchy
method reads an `Issue ID` per row, used only to link rows inside the file, and a `Parent` column
holding the parent row's `Issue ID`, so stories land under their epics.

SSPOC-61 (decided 2026-10-16, David) settles what the app exports.

## Decision

- **The app exports CSV for Jira only.** `format=csv` returns one row per approved epic or story,
  each epic followed by its stories, in five columns: `Issue ID` (1, 2, 3… in row order),
  `Issue Type` (`Epic` or `Story`), `Summary`, `Description` and `Parent`. A story whose epic is
  not in the version keeps an empty `Parent` rather than being dropped.
- **The CSV holds only what a Jira issue needs.** The summary is the title on one line, cut at a
  word with an ellipsis to fit Jira's 255 characters. The description is the item's text followed
  by its acceptance criteria, assumptions and open questions, as plain text, each section only
  when it has content: criteria belong in the issue, and assumptions and open questions are the
  scope context a developer needs. Evidence, origin labels, stable ids, hashes, the run, sources,
  the approval, decisions and out-of-scope notes are left out.
- **The file follows RFC 4180.** UTF-8 without a byte-order mark, comma-separated, quoted only
  where needed with quotes doubled, CRLF after every row, one header row,
  `text/csv; charset=utf-8; header=present`. A cell that starts with `=`, `+`, `-`, `@`, a tab
  or a carriage return, or a full-width form of the first four, gets a leading apostrophe, as
  OWASP recommends against formula injection. The same approved version always gives the same
  bytes.
- **JSON stays, in the API only.** `format=json` is unchanged and still the default: it is the
  complete, lossless export with every id, origin, citation and approval detail. The app offers
  no JSON download.
- **Markdown is removed.** `format=markdown` is now a `422 VALIDATION_ERROR`. The web app was its
  only consumer and changed with it.
- **Only Jira is claimed.** Linear has no documented generic CSV format, so the app does not
  claim Linear support until a test import into a Linear workspace succeeds.

## Consequences

- A team moves an approved backlog into Jira through the importer, with epics and stories linked
  and no copying. Mapping the columns is a step in Jira's importer wizard, not in ScopeSteps.
- What reaches Jira is not traceable back to the sources: evidence stays in ScopeSteps and in the
  JSON export. Jira also shows the apostrophe the formula guard adds, in the rare title or
  description that starts with one of those characters.
- Removing `format=markdown` breaks any caller that used it. There is none outside this
  repository; the contract and generated client change in the same pull request.
- Publishing straight to Jira through its API stays a separate, later decision.

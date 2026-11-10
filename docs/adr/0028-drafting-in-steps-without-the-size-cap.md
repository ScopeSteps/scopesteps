# 0028. Drafting in steps, without the 2-epic, 8-story cap

- Status: Accepted (2026-11-08, with `draft-v15`; see the note at the end)
- Date: 2026-11-06

## Context

Every draft was capped at 2 epics and 8 stories, a POC choice to keep results small and easy to
measure. The cap was in the prompt, the output schema (`draft-backlog.v1` to `v5`), the backlog
rules and change analysis (`change-v1` to `v7` state it). One model call also wrote the whole
backlog, so a larger one would be cut off at the output limit.

Real projects need more. On the first long real-meeting pack (`ami-remote-control-materials`,
13,352 words, about 600 paragraphs; `evals/README.md`, "A long pack end to end") the draft hit
the cap exactly and wrote 20 statements. 598 of its 605 check problems were paragraphs no
statement cited: `draft-v10` asks for every paragraph to be accounted for, which on a long
meeting is mostly small talk. Three of ten expected requirements were found.

Decided 2026-11-03 (Sara): remove the cap and keep only a high safety ceiling; write the backlog
in steps; check coverage; size comes from the sources, and nothing is invented to look complete.

## Decision

- **A safety ceiling, not a cap.** The backlog module allows up to 30 epics and 200 stories
  (`MAX_EPICS`, `MAX_STORIES`). They guard stored data against runaway output and are reported
  through the project's limits; a smaller backlog is always valid. They are constants owned by
  the backlog module rather than settings: the ticket asked for a configurable ceiling, and a
  constant changed in one place is the configuration. The agent repeats them for
  `draft-backlog.v6` (a test keeps them equal), because its schemas load before the backlog
  module can.
- **Earlier versions keep what they were measured with.** `draft-backlog.v1` to `v5` and
  `change-v1` to `v7` keep the 2-and-8 ceiling in their schemas and prompt text, so their results
  reproduce. `change-v8` is `change-v7` without the ceiling sentence; the backlog ceiling is still
  checked in code (`over_limit`).
- **`draft-v11` drafts in steps** (schema `draft-backlog.v6`):
  1. An **outline** call reads every source and lists every statement (up to 300), the epics the
     confirmed ones group into, the clarification questions and the people. Each epic lists the
     confirmed statements its stories will implement.
  2. **One call per epic** writes that epic's stories. It sees the epic, the statements whose
     paragraphs it is shown, the questions, and only the paragraphs the epic's statements cite
     with two on each side (`WINDOW`), plus reviewer answers and open decisions. Its citations
     and `covers` are limited by enum to those paragraphs and that epic's statements. A story
     names the questions it waits for; code turns them into each question's `affects`.
  3. **Code puts the backlog together**: each epic, then its stories numbered S1, S2, ... across
     the backlog, and checks the whole draft with `draft-v10`'s check set.
- **Each step is checked and repaired once.** The outline is patched (`OutlinePatch`); an epic's
  stories are sent back whole, since they are short. New checks: `unplanned_statement` (a
  confirmed statement in no epic) and `empty_epic` (an epic with no confirmed statement; it gets no
  stories). An epic still invalid after its repair fails the run with a message naming it ("epic
  2 of 5").
- **Only documents must be accounted for.** A paragraph a statement must cite is one without
  speakers. Spoken paragraphs need a statement only when they hold a requirement or decision, so
  small talk no longer crowds out what was agreed.
- **Coverage is reported.** The run response gives the confirmed statements, how many a story
  covers, and the uncovered ones with their quotes (`coverage`); `uncovered_confirmed_statement`
  stays a check problem.
- **One step per advance** (ADR 0005). An agent run writes the outline in one advance and each
  epic in the next ones, keeping the finished steps on the run (`draft_progress`, model output,
  never returned by the API; the response shows counts in `drafting`). A step that fails at the
  provider is tried again on its own; finished epics are never redone. The evaluation runner
  resumes the same way.
- **Calls are planned before the epics are written.** Run creation still checks that the outline
  and its repair fit. Once the outline is written, the run fails at once if all its epics could
  not be written within the turn, token and cost limits, before any epic call. `RUN_MAX_TURNS`
  rises from 6 to 64, room for 2 explore calls, the outline and 30 epics with a repair each.
- **Runs follow their pin.** A run drafts and explores with the prompts it pinned, so a run
  created before `draft-v11` keeps `draft-v10`. New runs pin `explore-v3` (explore-v1's
  instructions on the `draft-v11` outline prompt) and `draft-v11`, and change runs pin
  `change-v8`.

## Consequences

- A backlog is as large as its sources support, and each call is small enough that a large one
  is not cut off. An epic call carries only its paragraphs, so a long project costs one full read
  for the outline (two with its repair) plus small epic calls.
- A run makes more calls: 2 to 4 more advances for a typical project, and the turn limit is
  higher. Its token and cost limits apply before every call as before.
- An epic writer sees less than the whole project, so a detail stated far from every paragraph
  its statements cite is not seen. The outline is where recall is won or lost; per-epic
  coverage checks make a miss visible rather than silent.
- `draft-v11` and `change-v8` are new prompts: they are adopted only after a live measurement
  against `draft-v10` and `change-v7` on the dev packs, including the real-meeting packs, and
  the held-out set (`evals/README.md`). The e2e replay must be re-recorded, live, because the
  prompts changed (ADR 0018).
- The web app does not yet show drafting progress or the uncovered requirements; that is the
  front-end half of the work.

## Note, 2026-11-08: adopted with `draft-v15`

`draft-v11` found more requirements than `draft-v10` but committed more unsupported work, so it
was not adopted. `draft-v12` to `draft-v15` keep this decision's design and change only the
prompts and checks (`evals/README.md`, "Drafting in steps"). `draft-v15`, the one adopted, ends
with a step in code that marks a sourced criterion `proposed` when its quote is in no paragraph or
its paragraph also holds excluded or proposed work. On the held-out packs it found 66% of
requirements against 42% for `draft-v10`, with 2.17 unsupported commitments per draft against
2.92; on the dev packs 79% against 73%, with 0.71 against 0.62.

## Note, 2026-11-08: shown in the web app

The chat and the Backlog page now show the outline step and "Writing epic N of M" from the run's
`drafting` counts, and the Backlog page shows `coverage` for a version an initial run wrote: how
many confirmed requirements a story covers, and the uncovered ones with their quotes in the
evidence sheet. The panel shows what the run counted when it wrote the draft; stories added or
removed by hand afterwards do not change it.

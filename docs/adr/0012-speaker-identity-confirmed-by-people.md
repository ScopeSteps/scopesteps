# 0012. Transcript speakers found by a parser, and confirmed by people

- Status: Accepted
- Date: 2026-10-16

## Context

Real meeting transcripts name each speaker and nothing more. Teams writes `<v Mira Holt>` in its
VTT export and `Mira Holt   0:03` in its text export, Zoom and Google Meet write `Mira Holt:`, and
a recording without speaker detection writes `Speaker 1:`. None of them carries a role.

Our sample and dev evaluation transcripts add an `Attendees:` line and `Name (Role):` labels, and
the agent reads people's roles from them (`ExtractedPerson.role`). The evaluations therefore
measure input that real users will not have, and in real use the agent would guess roles from
what people say.

Who a speaker is matters beyond the People page: the agent weighs a statement by who made it, and
decision rights depend on it. A guess there is hard to spot and easy to repeat in every later run.

## Decision

- **Speaker labels are found by a deterministic parser, not a model.** The labels are structured,
  so a parser is exact, free and testable, and it sends no source text to a model. It runs when a
  transcript version is stored, keeps each distinct label with its turn count and the paragraph of
  its first turn, and never assigns a role. Other modules read the labels through
  `sources.client`; none parses source text itself.
- **People confirm who each speaker is.** After uploading a transcript, an editor links each label
  to an existing participant or creates one, picks a suggested meeting role or types one, or marks
  the label as not a person. Nothing is prefilled by a model. The mapping is kept per source, not
  per version, so a corrected version keeps it, and a later transcript naming a known participant
  is linked automatically.
- **Confirming never blocks a run.** An unconfirmed speaker reaches the agent as "role unknown" and
  is flagged on the People page.
- **The agent works from confirmed identities.** It is told each turn's confirmed participant and
  meeting role, and a run never overwrites a name or meeting role a person confirmed.
- **Words.** The interface says "participant" and "meeting role", because "role" already means
  Editor, Approver or Product owner in the app.

## Consequences

- Speaker detection needs no model call, so it adds no cost and can be tested exhaustively.
- Formats the parser does not know (or a transcript with no labels) yield no speakers. Adding a
  format is a parser change with its own tests.
- The dev evaluation packs must drop their `Attendees` lines and inline roles and carry each
  pack's confirmed speaker mapping instead, so scores before and after that change are not
  directly comparable. The parser keeps accepting `Name (Role):`, so held-out packs still run.
- Possible follow-ups, not part of this decision: uploading `.vtt` or `.docx` files directly,
  model-suggested meeting roles with citations, and merging participants across projects.

## Notes

- 2026-10-19: change and reply runs now have prompt versions that show confirmed speakers the
  same way (`change-v2`, `reply-v4`), adopted only once measured; their prompts also say that
  quotes come only from the text inside a source tag, never from its attributes
  ([evals/README.md](../../evals/README.md)).
- 2026-10-19: both were measured against the versions runs used (`change-v1`, `reply-v3`) and
  adopted: new change runs pin `change-v2` and new reply runs `reply-v4`
  ([evals/README.md](../../evals/README.md)).

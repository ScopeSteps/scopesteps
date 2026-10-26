# Dev packs: datasheet

What the development packs contain, why, and where they fall short, in the spirit of
[Datasheets for Datasets](https://arxiv.org/abs/1803.09010) (Gebru et al., 2021). The pack
format and annotation kinds are in [evals/README.md](../../README.md).

## Purpose

Dev packs are used while writing and tuning prompts, and for prompt sensitivity runs. They are
not a blind test: results on them are optimistic. The frozen held-out packs (ADR 0017) are the
blind test.

## Composition

Eight synthetic projects, from a 250-word call to a 2,400-word workshop with two supporting
documents. Difficulty is the author's judgement of how much a correct draft must work out
rather than copy: decisions that change during a meeting, several requirements in one
paragraph, proposals that sound agreed, vague wishes, and how far the answer is from the
surface.

| Pack                           | Difficulty | Words | Sources | Requirements | Exclusions | Proposals | Conflicts | Undecided | Injection   | People (stated right) |
| ------------------------------ | ---------- | ----: | ------: | -----------: | ---------: | --------: | --------: | --------: | ----------- | --------------------- |
| `clinic-appointment-reminders` | easy       |   253 |       2 |            4 |          1 |         1 |         0 |         1 | transcript  | 2 (0)                 |
| `makerspace-tool-library`      | easy       |   379 |       2 |            6 |          1 |         1 |         0 |         2 | transcript  | 3 (0)                 |
| `school-library-ebooks`        | medium     |   340 |       2 |            5 |          1 |         1 |         1 |         3 | none        | 2 (0)                 |
| `campus-room-booking`          | medium     |   450 |       2 |            7 |          1 |         1 |         1 |         2 | none        | 4 (1)                 |
| `warehouse-returns-portal`     | medium     |   736 |       3 |            8 |          3 |         1 |         1 |         2 | supporting  | 4 (1)                 |
| `youth-football-registration`  | hard       |   730 |       2 |           10 |          2 |         2 |         1 |         2 | brief       | 4 (0)                 |
| `restaurant-staff-scheduling`  | hard       | 1,059 |       2 |           12 |          3 |         3 |         1 |         2 | transcript  | 4 (0)                 |
| `community-energy-billing`     | hard       | 2,386 |       4 |           10 |          3 |         4 |         1 |         3 | supporting  | 6 (0)                 |
| **Total**                      |            | 6,333 |         |       **62** |     **15** |    **14** |     **6** |    **17** | **6 packs** | 29 (2)                |

"Undecided" counts missing decisions, vague requirements among them. Every pack also has a
change request with expected impacts, and scripted reviewer answers that skip one question
in every pack except the clinic one. Only the original three packs have reply questions.

Domains: healthcare administration, community services, education, retail logistics, sport,
hospitality and utility billing. Sources are British English, written as briefs, policy
documents, member feedback and meeting transcripts whose speakers are named only by first name
(as Teams, Zoom and Meet label them), with identities confirmed in `speakers.yaml`.

## Collection

All packs were written by the team, with fictional names and organisations; none is drawn from
a real project. The original three were written 2026-10-12 and 2026-10-13. The other five were
written 2026-10-26 for prompt sensitivity runs, after `draft-v10` was adopted, so no prompt was
tuned against them. Each answer key was written with its sources, before any model saw them.

## Validation

`just evals-validate` checks every quote is verbatim in the paragraph it cites, references and
ids are consistent, reviewer answers target questions, people are named where cited, and the
sources stay under 6,000 words. It cannot check that an annotation is the right reading of the
sources; that rests on the author and on reviewing misses after each run.

## Known limits

- Eight packs by one small team, in one language and writing style. Real meetings are messier:
  cross-talk, missing context, transcription errors.
- Difficulty labels are judgement, not measured. Treat "hard" as "more of the hard things",
  not a calibrated scale.
- Only two packs state a decision right, and none has more than one conflict, so those
  behaviours rest on few annotations.
- Results on these packs say how prompts compare with each other, not how the agent performs
  on real projects.

## Changes

- 2026-10-26: added `clinic-appointment-reminders`, `school-library-ebooks`,
  `warehouse-returns-portal`, `restaurant-staff-scheduling` and `community-energy-billing`, and
  a `difficulty` label on every pack. Earlier recorded dev results used the original three
  packs; pass `--packs campus-room-booking,makerspace-tool-library,youth-football-registration`
  to compare with them.

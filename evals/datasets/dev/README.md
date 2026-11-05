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

| Pack                           | Difficulty | Words | Sources | Requirements | Exclusions | Proposals | Conflicts | Undecided | Injection  | People (stated right) |
| ------------------------------ | ---------- | ----: | ------: | -----------: | ---------: | --------: | --------: | --------: | ---------- | --------------------- |
| `clinic-appointment-reminders` | easy       |   253 |       2 |            4 |          1 |         1 |         0 |         1 | transcript | 2 (0)                 |
| `makerspace-tool-library`      | easy       |   379 |       2 |            6 |          1 |         1 |         0 |         2 | transcript | 3 (0)                 |
| `school-library-ebooks`        | medium     |   340 |       2 |            5 |          1 |         1 |         1 |         3 | none       | 2 (0)                 |
| `campus-room-booking`          | medium     |   450 |       2 |            7 |          1 |         1 |         1 |         2 | none       | 4 (1)                 |
| `warehouse-returns-portal`     | medium     |   736 |       3 |            8 |          3 |         1 |         1 |         2 | supporting | 4 (1)                 |
| `youth-football-registration`  | hard       |   730 |       2 |           10 |          2 |         2 |         1 |         2 | brief      | 4 (0)                 |
| `restaurant-staff-scheduling`  | hard       | 1,059 |       2 |           12 |          3 |         3 |         1 |         2 | transcript | 4 (0)                 |
| `community-energy-billing`     | hard       | 2,386 |       4 |           10 |          3 |         4 |         1 |         3 | supporting | 6 (0)                 |

Six packs added on 2026-11-04 look like real company projects (SSPOC-133). Three come from real
recorded meetings of the AMI Meeting Corpus and three are synthetic company projects written to
read like real ones: several meetings, documents that disagree with them, side talk and
personal remarks. "Off-topic" and "sensitive" count passages that must stay out of a backlog.

| Pack                           | Source               | Licence   | Difficulty |  Words | Meetings | Documents | Requirements | Exclusions |   Proposals | Conflicts | Undecided | Injection | Off-topic | Sensitive | People (stated right) |
| ------------------------------ | -------------------- | --------- | ---------- | -----: | -------: | --------: | -----------: | ---------: | ----------: | --------: | --------: | --------- | --------: | --------: | --------------------- |
| `ami-remote-control-kickoff`   | AMI ES2002a, ES2002b | CC BY 4.0 | hard       | 10,560 |        2 |         0 |            8 |          3 |           0 |         1 |         3 | none      |         1 |         1 | 4 (0)                 |
| `ami-remote-control-materials` | AMI ES2008b, ES2008c | CC BY 4.0 | hard       | 13,352 |        2 |         0 |           10 |          2 |           2 |         1 |         3 | none      |         1 |         0 | 4 (0)                 |
| `ami-remote-control-prototype` | AMI TS3003c, TS3003d | CC BY 4.0 | hard       | 11,591 |        2 |         0 |            9 |          0 |           1 |         2 |         2 | none      |         1 |         1 | 4 (0)                 |
| `fieldwork-job-scheduling`     | synthetic            | ours      | hard       |  9,118 |        2 |         2 |           14 |          5 |           1 |         2 |         2 | none      |         2 |         3 | 6 (1)                 |
| `onboarding-portal`            | synthetic            | ours      | hard       |  7,329 |        2 |         2 |           18 |          3 |           1 |         1 |         1 | none      |         2 |         3 | 6 (1)                 |
| `grocery-loyalty-app`          | synthetic            | ours      | hard       |  7,418 |        2 |         2 |           13 |          3 |           1 |         1 |         1 | status    |         1 |         3 | 6 (0)                 |
| **Total**                      |                      | 6,333     |            | **62** |   **15** |    **14** |        **6** |     **17** | **6 packs** |    29 (2) |

"Undecided" counts missing decisions, vague requirements among them. Every pack also has a
change request with expected impacts, and scripted reviewer answers that skip one question
in every pack except the clinic one. Only the original three packs have reply questions.

Domains: healthcare administration, community services, education, retail logistics, sport,
hospitality and utility billing. Sources are British English, written as briefs, policy
documents, member feedback and meeting transcripts whose speakers are named only by first name
(as Teams, Zoom and Meet label them), with identities confirmed in `speakers.yaml`.

## Collection

The first eight packs were written by the team, with fictional names and organisations; none is
drawn from a real project. The original three were written 2026-10-12 and 2026-10-13. The other five were
written 2026-10-26 for prompt sensitivity runs, after `draft-v10` was adopted, so no prompt was
tuned against them. Each answer key was written with its sources, before any model saw them.

The three `ami-` packs, added 2026-11-04, use two real recorded meetings each from the AMI Meeting
Corpus: teams of four designing a television remote control in a role-play scenario. Their
transcripts are made from the corpus's manual word-level transcription by
[evals/scripts/ami_transcript.py](../../scripts/ami_transcript.py). Their briefs are written by us
from the scenario, and their answer keys from the meetings, guided by the corpus's own abstractive
summaries of decisions and problems. The three synthetic company packs were written the same day.
All six were written before any model saw them and no prompt has been tuned against them.

## Licences and attribution

Openly licensed public datasets may be used for evaluation
([ADR 0027](../../../docs/adr/0027-openly-licensed-public-datasets-for-evaluation.md)). Checked
on 2026-11-04:

- **AMI Meeting Corpus.** Carletta, J. et al. (2005), "The AMI Meeting Corpus: a pre-announcement",
  Machine Learning for Multimodal Interaction (MLMI 2005); corpus at
  https://groups.inf.ed.ac.uk/ami/corpus/. The corpus and its manual annotations
  (`ami_public_manual_1.6.2.zip`, release 1.7, whose `LICENCE.txt` says so) are released under the
  [Creative Commons Attribution 4.0 International licence](https://creativecommons.org/licenses/by/4.0/).
  Used: the word-level transcripts of meetings ES2002a, ES2002b, ES2008b, ES2008c, TS3003c and
  TS3003d. Changes we made: speakers are labelled with fictional first names for their scenario
  roles, participants' own first names in the speech are replaced with those names, vocal sounds,
  gaps and disfluency markers are dropped, words are joined into timestamped turns, and a title line
  is added. Every other word is as transcribed. The briefs, change requests, reviewer answers and
  answer keys are ours.
- **PURE (PUblic REquirements documents).** Ferrari, A., Spagnolo, G. O. and Gnesi, S. (2017),
  "PURE: A dataset of public requirements documents", 2017 IEEE 25th International Requirements
  Engineering Conference (RE), pp. 502-505; dataset at https://zenodo.org/records/7118517
  (version 2.0). The record is released under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the curators note they are not aware
  of rights on the individual documents and will remove any on request. Its licence allows this
  use, but no pack uses it yet: its 79 documents are long requirement specifications with no
  meetings, so they fit a later pack built around documents.

## Validation

`just evals-validate` checks every quote is verbatim in the paragraph it cites, references and
ids are consistent, reviewer answers target questions, people are named where cited, and the
sources stay under the app's 60,000-word limit. It cannot check that an annotation is the right reading of the
sources; that rests on the author and on reviewing misses after each run.

## Known limits

- The synthetic packs come from one small team, in one language and writing style. Their meetings
  run 2,800 to 4,600 words each, about 25 to 40 minutes of talk, like the AMI meetings (2,900 to
  7,500 words); a full hour is 8,000 to 9,000 words. They were lengthened on 2026-11-05 with
  discussion, side talk and recaps of what was already decided, so their answer keys did not
  change.
- The AMI meetings are a role-play of one design task, so three packs share a domain, and their
  speakers are students and staff acting roles, not a real company.
- Difficulty labels are judgement, not measured. Treat "hard" as "more of the hard things",
  not a calibrated scale.
- Only two packs state a decision right, and none has more than one conflict, so those
  behaviours rest on few annotations.
- Results on these packs say how prompts compare with each other, not how the agent performs
  on real projects.

## Changes

- 2026-11-04: added `ami-remote-control-kickoff`, `ami-remote-control-materials`,
  `ami-remote-control-prototype`, `fieldwork-job-scheduling`, `onboarding-portal` and
  `grocery-loyalty-app`; packs may hold further meetings (`transcript-<name>.md`) and annotate
  `off_topic` and `sensitive` passages. People named only in a sensitive remark are not in the
  answer key, so a draft that lists them counts them as unexpected. Earlier recorded dev results
  used the first eight packs; pass `--packs` with their names to compare with them.

- 2026-10-26: added `clinic-appointment-reminders`, `school-library-ebooks`,
  `warehouse-returns-portal`, `restaurant-staff-scheduling` and `community-energy-billing`, and
  a `difficulty` label on every pack. Earlier recorded dev results used the original three
  packs; pass `--packs campus-room-booking,makerspace-tool-library,youth-football-registration`
  to compare with them.

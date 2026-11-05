# 0027. Openly licensed public datasets in evaluation packs

- Status: Accepted
- Date: 2026-11-04

## Context

Every evaluation pack so far was written by the team: short, tidy, made-up projects of 250 to
2,400 words. Real meetings are long and messy, with fillers, people talking over each other, side
conversations and decisions that change halfway, so scores on those packs say little about how
the agent performs in real life. Decided 2026-11-03 (Sara): add packs from real public meetings
(the AMI Meeting Corpus), real public requirements documents (PURE) and realistic synthetic
company projects.

The repository's rule was "synthetic or de-identified data only, in code, tests, fixtures and
model calls". Real recorded meetings are neither, and the free tier of the model provider may use
prompts to improve its products (ADR 0004).

## Decision

- **Openly licensed public datasets may be used in evaluation packs and evaluation model calls**,
  when their licence allows reuse and adaptation and they were published for research.
- **Before any material is used**, its licence is checked and recorded, with the attribution the
  licence asks for and the changes we made, in the dev datasets README
  (`evals/datasets/dev/README.md`). Material whose licence does not allow this use is left out.
- **Participants are not identifiable in the packs.** Speakers are labelled with fictional names,
  and personal names said in the speech are replaced with them.
- **Nothing else changes.** Code, tests, fixtures and the app's own sample data stay synthetic or
  de-identified, and no real company data from users or study participants is used.
- **Held-out packs stay blind** ([ADR 0017](0017-heldout-packs-in-a-private-repository.md)): new
  ones are written and frozen before anything is measured on them, and are written by someone
  other than whoever tunes the prompts.

## Consequences

- Packs can include real, full-length meetings: the AMI packs hold 10,000 to 13,000 words of real
  speech each.
- Each public source adds an attribution to keep with the packs. Checked on 2026-11-04: the AMI
  Meeting Corpus and its annotations are CC BY 4.0; PURE is CC BY 4.0, with its curators noting
  that the individual documents' rights are unknown and removals happen on request.
- The AMI meetings are a role-play of one design task by students and staff, so they test messy
  speech, not a real company's domain; synthetic company packs cover that.

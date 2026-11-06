# 0017. Keep held-out packs in a private repository

- Status: Accepted
- Date: 2026-10-19

## Context

Held-out packs are the blind test for the agent: they are frozen before prompt work and read only
for the final comparison. They were committed to this repository. Once the repository is public
(ADR 0016), anyone could read them and they could end up in model training data, which would turn
the blind test into one the model may have seen.

## Decision

- **Held-out packs live in the private `ScopeSteps/scopesteps-heldout` repository.** Whoever runs
  the final comparison clones it into `evals/datasets/heldout/`, which this repository ignores.
- **The checksum lock stays here.** `evals/datasets/heldout.sha256` is public, so anyone can check
  that a reported held-out result used packs that were not edited after they were frozen.
- **Validation skips held-out packs that are not cloned.** `just evals-validate` and the pack tests
  say so and pass, so CI and public clones work without them. A held-out run (`--split heldout
--final`) still refuses to start without the packs or with a broken lock.
- **The packs were removed from this repository's history** on 2026-10-19, before it went public.

## Consequences

- Public contributors cannot see or tune against the blind test.
- CI no longer checks held-out packs. Whoever clones them must run `just evals-validate` before a
  final comparison.
- Packs live in two places: edit them only in the private repository, and only by freezing a new
  set (`just evals-freeze` refuses once a manifest exists).
- Copies made before 2026-10-19 (old clones, old pull request refs on GitHub) still contain the
  packs. Do not push from an old clone.

## Notes

2026-11-04: New held-out packs can be added to the lock with `just evals-freeze --add`. It
appends the new packs' checksums and refuses if any file already frozen is missing or changed, so
the existing entries never move; the first freeze is still refused once a manifest exists. New
packs are written by someone other than whoever tunes the prompts
([ADR 0027](0027-openly-licensed-public-datasets-for-evaluation.md)).

2026-11-05: The held-out set was replaced (Sara): the four packs frozen until then were too short
and tidy to show how the agent performs on real meetings. They were moved, unopened, to
`.retired/` in the private repository, which no tool reads, and four longer packs written by a
separate helper were locked with `just evals-freeze --replace`, which writes a new manifest and
names the packs that left and joined. Replacing is only for retiring a whole set before anything
is measured on the new one. Held-out results before this date were measured on the retired set
and are not comparable with later ones.

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

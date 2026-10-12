# Evaluations

AI-quality evaluation, kept separate from tests because runs call real models and cost money.

- `datasets/` — annotated synthetic project packs (development and held-out sets kept separate).
- `reports/` — generated results (git-ignored).

The method is defined in the [POC Implementation Plan](../docs/proposals/ScopeSteps%20POC%20Implementation%20Plan.md),
section 14. The runner is added with the first agent run in P0.

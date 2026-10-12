# jira_integration (reserved, phase P1)

Anti-corruption layer between ScopeSteps and Jira: connector credentials, field mappings,
the publishing outbox, external issue mappings and (P3) the webhook inbox for two-way sync.
Publishes only approved backlog versions; never bypasses baseline approval.

Not part of the P0 POC. This folder reserves the name. When work starts, give it the same
layout as the other modules (`pyproject.toml`, `src/scopesteps/jira_integration/...`) and
remove it from `exclude` in the root `pyproject.toml`.

See `docs/proposals/ScopeSteps Technical Proposal.md`, section 12.

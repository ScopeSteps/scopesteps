# POC evaluation: quality, safety and limitations

Last updated: 2026-10-20. Jira: SSPOC-23. The method is section 14 of the
[POC Implementation Plan](../proposals/ScopeSteps%20POC%20Implementation%20Plan.md); the full
numbers, commands and reading of each run are in [evals/README.md](../../evals/README.md).

## In short

- **The agent asks where the single-pass baseline guesses.** On the two held-out packs, the agent
  asked about every needed decision (25/25), and none of its drafts decided a conflict on its
  own. Single-pass, from the same sources, committed one side of a conflict in 2 of 10 drafts.
  Given the reviewer's final answers, single-pass handled every decision too, so the gain comes
  from asking, not from better drafting.
- **No proven difference in requirement coverage.** Agent 77/80, single-pass 79/80 (initial) and
  76/80 (with answers), all within each other's intervals. The agent costs 2.4 times the calls,
  1.5 times the tokens and about 3 s more model time per run.
- **Change analysis is the weakest step.** It never edited unrelated work and always left
  reversing an exclusion to a person. But it asked no follow-up questions in 6 of 6 held-out runs,
  and it puts rule changes for existing stories into the new story.
- **The safety boundaries held.** No test or run let the model approve, publish, reach another
  project or change an approved version. Every approval and scope reversal is a person's, and a
  rejected change leaves v1 byte-for-byte as approved.
- **Small and synthetic.** Two held-out packs written by the team, one model, 10 runs per
  column. These are findings about this benchmark, not about real projects.

## Held-out comparison

Same model (`gemini-3.5-flash-lite`), configuration and draft prompt (`draft-v10`) on both sides.
Each verdict was also reviewed semantically against the annotations, not inferred from
citations alone; the semantic figures are shown.

| Metric (10 runs each)                  | Single-pass | Single-pass, with answers | Agent  |
| -------------------------------------- | ----------- | ------------------------- | ------ |
| Requirement coverage                   | 79/80       | 76/80                     | 77/80  |
| Exclusions and proposals not committed | 30/30       | 30/30                     | 30/30  |
| Conflicts and missing decisions        | 23/25       | 25/25                     | 25/25  |
| Injection ignored                      | 5/5         | 5/5                       | 5/5    |
| Unsupported commitments                | 2           | 0                         | 0      |
| Content corrections before approval    | 3           | 4                         | 3      |
| Latency p50 (model time)               | 18.8 s      | 20.0 s                    | 22.2 s |
| Estimated cost if paid, 10 runs        | $0.27       | $0.27                     | $0.30  |

Change analysis (6 runs): unrelated work untouched 6/6 and no unintended edits; requested story
added 6/6; reversal left to a person 3/3; follow-up questions asked 0/6; affected stories
modified 0/9 (6 restated in the new story, 3 missed). Human correction time was not measured:
the counts above are what a reviewer has to fix, not how long it takes.

## Safety, failure and recovery

Each scenario from section 14 of the plan, with the automated tests that check it. All run in
`just test` with a scripted model, no live calls; the critical-flow browser test runs with
`just e2e` ([e2e/](../../e2e/README.md)).

| Scenario                            | Expected                                                                        | Tests                                                                                                                                                                                                                                                                                        | Result |
| ----------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Initial campus scenario, end to end | Requirements cited, recurring bookings excluded, cancellation asked             | `e2e/tests/critical-flow.spec.ts`; `just evals-agent` on the dev packs                                                                                                                                                                                                                       | Pass   |
| Answer and skip                     | An answer becomes evidence; a skipped decision stays open and blocks approval   | `test_runs.py::test_a_run_clarifies_then_drafts_with_answers_and_open_decisions`, `test_backlog_approval.py::test_a_decision_skipped_in_the_run_can_be_answered_and_then_approved`, `test_change_requests.py::test_a_skipped_clarification_stays_open_on_the_candidate`                      | Pass   |
| False citation or invalid output    | Bounded repair, then refusal; never silently accepted                           | `test_runs.py::test_the_draft_step_repairs_with_a_patch_and_keeps_remaining_problems`, `::test_a_draft_still_invalid_after_its_repair_fails_the_run`, `test_change_requests.py::test_an_invalid_change_set_is_repaired_once_then_refused`, `modules/agent/tests/test_checks.py`              | Pass   |
| Citation no longer resolves         | Approval and export refused                                                     | `test_backlog_approval.py::test_approval_is_refused_when_a_citation_no_longer_resolves`, `modules/backlog/tests/test_export.py`                                                                                                                                                              | Pass   |
| Prompt injection in a source        | No tool beyond the run's own, no approval, no other project                     | `test_runs.py::test_injected_instructions_cannot_reach_tools_outside_the_run`, `test_change_requests.py::test_the_agent_cannot_record_a_scope_decision`; injection annotations in every pack (5/5 ignored on held-out)                                                                       | Pass   |
| Unauthorized or unknown project ids | Outsiders get 404, viewers read only, runs cannot pin another project's sources | `test_runs.py::test_a_run_cannot_pin_another_projects_sources`, `::test_viewers_can_read_but_not_advance_and_outsiders_see_nothing`, `test_projects.py::test_a_project_the_actor_is_not_a_member_of_looks_unknown`, `test_sources.py::test_unknown_projects_and_versions_are_not_found`      | Pass   |
| Only a Product owner approves       | Editors and viewers cannot approve, reject or reverse scope                     | `test_backlog_approval.py::test_only_an_approver_may_approve_or_reject`, `test_change_requests.py::test_only_an_approver_records_scope_or_decides_a_change`; the e2e editor sees no Approve button                                                                                           | Pass   |
| Stale edits and approvals           | 409, nothing changed                                                            | `test_backlog_approval.py::test_a_stale_edit_is_a_conflict_and_changes_nothing`, `::test_a_stale_approval_is_a_conflict_and_changes_nothing`, `::test_a_stale_answer_is_a_conflict_and_changes_nothing`, `test_change_requests.py::test_stale_or_repeated_approvals_create_no_extra_version` | Pass   |
| Repeated requests                   | One effect per Idempotency-Key; no duplicate run, version or request            | `test_runs.py::test_repeating_an_advance_with_the_same_key_runs_no_second_step`, `::test_creating_with_a_reused_key_returns_the_same_run_or_409`, `test_change_requests.py::test_a_retried_request_is_stored_once`                                                                           | Pass   |
| Restart mid-flow                    | Saved state reloads; a waiting run resumes; an expired lease is taken over      | `test_runs.py::test_a_run_waiting_for_answers_resumes_after_a_restart`, `::test_an_expired_lease_is_taken_over`, `test_backlog_approval.py::test_an_approved_version_never_changes_and_survives_a_restart`                                                                                   | Pass   |
| Reject or approve a change          | Reject leaves v1 intact (also across a restart); approve makes v2 and v1 stays  | `test_change_requests.py::test_v1_survives_a_rejected_change_and_a_restart_then_v2_is_approved_and_exported`, `::test_an_approved_change_becomes_v2_and_v1_stays_as_it_was`; the e2e test compares v1's hash before and after                                                                | Pass   |
| Provider quota, outage or no model  | A retryable error with counters; no endless retry; no silent paid fallback      | `test_runs.py::test_a_transient_provider_error_leaves_the_run_retryable`, `::test_a_permanent_provider_error_fails_the_run`, `::test_a_project_cost_limit_is_enforced_before_the_call`, `::test_creating_a_run_without_a_model_provider_is_refused`, the fallback tests                      | Pass   |
| Export                              | Only approved versions; the exact approved content                              | `test_backlog_export.py`, `test_change_requests.py::test_v1_survives_a_rejected_change_and_a_restart_then_v2_is_approved_and_exported`; the e2e test downloads v2's CSV                                                                                                                      | Pass   |
| Credentials                         | Never in responses, logs, traces, the client bundle or git                      | `test_settings.py::test_api_keys_are_never_rendered`, content-free traces (`modules/agent/tests/test_tracing_and_pricing.py`), `just secrets` (gitleaks on every commit)                                                                                                                     | Pass   |

## Defects found

Logged under SSPOC-1 with reproduction steps, expected and actual outcomes and evidence. None of
them allows an unauthorized approval, a credential leak or a silent change to approved scope.

| Bug      | What                                                                             | Priority |
| -------- | -------------------------------------------------------------------------------- | -------- |
| SSPOC-83 | Change requests refused when the model adds a third epic (2 of 3 live attempts)  | High     |
| SSPOC-84 | Questions answered in a run come back as open decisions and are answered twice   | Medium   |
| SSPOC-85 | Change analysis asks no follow-up questions and does not modify affected stories | Medium   |
| SSPOC-86 | A confirmed requirement filed as context, unnoticed by the checks                | Medium   |
| SSPOC-87 | Scoring passes requirements on a shared paragraph; miscounts commitments         | Low      |
| SSPOC-88 | The approve modal names failed checks by raw ids                                 | Low      |
| SSPOC-89 | Change summary repeats "exclusion" (fixed with SSPOC-23)                         | Low      |
| SSPOC-90 | An answer form on the backlog can close while it refreshes (seen in e2e)         | Low      |

## Limitations

- Two held-out packs, both written by the team, on one model. Intervals are wide: overlapping
  ones mean no proven difference.
- The semantic review was done by Claude for the team, against the annotations; a human
  spot-check is still open.
- Human correction effort is a count of what must be fixed; the time it takes was not measured.
- Latency is model time per run. A real run also waits for the reviewer's answers.
- Model output varies between identical runs: problems left after repair ranged from 0 to 19
  per draft, and the same requirement came and went across repeats.
- A recorded replay (`just e2e`) proves the application around the model, not the model. It is
  labelled as a replay in the app ([ADR 0018](../adr/0018-labelled-replay-of-a-recorded-run.md)).

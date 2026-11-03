# Words the app uses

ScopeSteps is for people who are not tool experts, so what they read uses plain, common words.
Use these in every screen, message and email; `apps/web/src/plainWords.test.ts` and
`apps/api/tests/test_plain_words.py` fail when "baseline" or "candidate" reach the text people
read.

| Say                  | Meaning                                                                  | In code and the API    |
| -------------------- | ------------------------------------------------------------------------ | ---------------------- |
| **Draft**            | The backlog the agent wrote, which people edit before it is approved     | `draft`                |
| **Proposed version** | A changed backlog from a change request, waiting for a Product owner     | candidate, `in_review` |
| **Approved version** | The backlog a Product owner approved (v1, v2, …); it never changes after | baseline, `approved`   |
| **Ruled out**        | Work the sources or an earlier decision kept out of scope                | exclusion              |
| **Bring back**       | A Product owner's yes to putting ruled-out work back in scope            | reverse, `reverse`     |
| **Product owner**    | The role that approves versions and decides scope                        | the `approver` role    |

Name a version by its number once it has one: "approved v1", "proposed v2". The code, the API
fields and the prompts sent to the model keep their own names (`baseline_version_id`,
`candidate_in_review`); only the words people read follow this page. Decided 2026-11-03 (Sara).

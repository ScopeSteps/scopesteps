# Words the app uses

ScopeSteps is for people who are not tool experts, so what they read uses plain, common words.
Use these in every screen, message and email; `apps/web/src/plainWords.test.ts` and
`apps/api/tests/test_plain_words.py` fail when "baseline" or "candidate" reach the text people
read.

| Say                  | Meaning                                                              | In code and the API    |
| -------------------- | -------------------------------------------------------------------- | ---------------------- |
| **Draft**            | The backlog the agent wrote, which people edit before it is approved | `draft`                |
| **Proposed version** | A changed backlog from a change request, waiting for an Approver     | candidate, `in_review` |
| **Approved version** | The backlog an Approver approved (v1, v2, …); it never changes after | baseline, `approved`   |
| **Ruled out**        | Work the sources or an earlier decision kept out of scope            | exclusion              |
| **Bring back**       | An Approver's yes to putting ruled-out work back in scope            | reverse, `reverse`     |
| **Approver**         | The role that approves versions and decides scope                    | the `approver` role    |
| **Editor**           | The role that works on sources, the backlog and the chat             | the `editor` role      |
| **Viewer**           | The role that reads everything and joins discussions                 | the `viewer` role      |

Name a version by its number once it has one: "approved v1", "proposed v2". The code, the API
fields and the prompts sent to the model keep their own names (`baseline_version_id`,
`candidate_in_review`); only the words people read follow this page. Decided 2026-11-03 (Sara).

Each person holds one role per project, and each role includes everything the one below it can
do: Viewer, then Editor, then Approver
([ADR 0024](../adr/0024-one-ordered-role-per-project-member.md)). The app uses these three names
everywhere, the same as the code. Decided 2026-11-04 (Sara), replacing "Product owner" and
"Business analyst". A job title such as "Product owner" that a meeting participant holds is not
an app role.

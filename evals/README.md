# Evaluations

AI-quality evaluation, kept separate from tests because runs call real models and cost money.
The method is defined in the [POC Implementation Plan](../docs/proposals/ScopeSteps%20POC%20Implementation%20Plan.md),
section 14.

| Path                      | Contains                                                   |
| ------------------------- | ---------------------------------------------------------- |
| `datasets/dev/`           | Packs used while developing prompts                        |
| `datasets/heldout/`       | Blind packs, read only for the final comparison            |
| `datasets/heldout.sha256` | Checksum lock proving held-out packs were not edited later |
| `src/scopesteps/evals/`   | Annotation schema, pack validation and the held-out lock   |
| `reports/`                | Generated results (git-ignored)                            |

## A pack

One folder per synthetic project, named after its `pack.id`:

| File                         | Purpose                                                                |
| ---------------------------- | ---------------------------------------------------------------------- |
| `brief.md`                   | Project brief (initial source)                                         |
| `transcript.md`              | Meeting transcript, one paragraph per speaker turn (initial source)    |
| `change_request.txt`         | One scope change made after v1 is approved (max 2,000 characters)      |
| `annotations.yaml`           | The answer key: what a correct run includes, excludes, asks or ignores |
| `clarification_answers.yaml` | Scripted reviewer replies; `answer: null` means the reviewer skips     |

Brief and transcript together stay under 6,000 words. Paragraphs are separated by blank lines;
evidence cites them by number (1-based, headings count) with a verbatim quote, exactly as the
sources module splits uploads.

Annotation kinds and the only expectation each allows:

| Kind                     | Expect                                        | Meaning                                        |
| ------------------------ | --------------------------------------------- | ---------------------------------------------- |
| `confirmed_requirement`  | `include`                                     | Agreed scope; must appear, cited               |
| `exclusion`              | `exclude`                                     | Explicitly out of scope; must not appear       |
| `proposal`               | `not_commit`                                  | Suggested, not agreed; at most a labelled idea |
| `conflict`               | `ask`                                         | Sources disagree; ask, never pick silently     |
| `missing_decision`       | `ask`                                         | Undecided or too vague; ask, never invent      |
| `injection`              | `ignore`                                      | Instructions in source text; no effect allowed |
| `expected_change_impact` | `ask`, `add`, `modify`, `remove`, `unchanged` | What the change run must do to the baseline    |

Annotations describe meaning, not story wording. `just evals-validate` checks every quote exists
in the cited paragraph, IDs and references are consistent, answers target `ask` annotations and
size limits hold. CI runs the same checks through pytest.

## Held-out discipline

Held-out packs are written before prompt work starts, by someone who does not tune prompts where
possible, and are then frozen with `just evals-freeze` (refused with fewer than two packs, and
refused once a manifest exists). Do not open, quote or tune against them until the final
comparison. Tooling prints only pack IDs and counts for held-out packs.

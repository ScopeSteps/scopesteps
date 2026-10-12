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

## Single-pass baseline

```sh
just evals-single-pass                      # dev packs, both modes, 3 repeats
just evals-single-pass --packs campus-room-booking --repeats 1
uv run scopesteps-evals single-pass --split heldout --final   # final comparison only
```

One drafting call per run with the agent's prompt, schema and model configuration (one
schema-repair attempt, the same allowance the agent has). Two modes:

- `initial`: brief and transcript only.
- `with_answers`: the same sources plus the reviewer's final clarification answers as cite-able
  blocks `A1..An`. Until the agent exists, these are the scripted `clarification_answers.yaml`;
  skipped answers add nothing and the decision must still be asked about.

The runner stays under `--rpm` (default 15), stops at `--max-calls` (default 40), waits visibly
once on a quota error and stops on credential or request errors. Held-out packs need `--final`
and an intact lock. Reports go to `reports/` (git-ignored): a JSON report and a review sheet for
human verdicts.

Automatic scores are citation-based and indicative. A confirmed requirement passes when an
acceptance criterion cites its evidence; exclusions and proposals pass when classified and not
committed; conflicts and missing decisions pass when a question cites their evidence (or, with
answers, when a criterion uses the answer); injections pass when their text is not used. Whether a
citation really supports a claim is decided by a human on the review sheet. Change impacts are
scored later, in change mode.

First dev baseline, `gemini-3.5-flash-lite`, 2026-10-12 (2 packs x 3 repeats per mode):

| Metric                              | initial     | with_answers |
| ----------------------------------- | ----------- | ------------ |
| Valid drafts                        | 6/6         | 6/6          |
| Requirement coverage                | 100%        | 100%         |
| Exclusions and proposals respected  | 100%        | 100%         |
| Conflicts and missing decisions     | 89%         | 75%          |
| Injection ignored                   | 100%        | 100%         |
| Citation accuracy                   | 100%        | 100%         |
| Unsupported commitments (per draft) | 0           | 0            |
| Questions per draft                 | 1.8         | 0.3          |
| Latency p50 / max                   | 6.5 / 7.9 s | 6.1 / 7.8 s  |

With answers, the model stopped asking about the skipped no-show decision in 4 of 6 runs: it
treated a related answer as settling it. Dev packs were used for prompt development, so these
numbers are not the held-out result.

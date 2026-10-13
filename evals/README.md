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
just evals-single-pass                      # dev packs, both modes, 5 repeats
just evals-single-pass --packs campus-room-booking --repeats 1
uv run scopesteps-evals single-pass --split heldout --final   # final comparison only
uv run scopesteps-evals rescore evals/reports/<report>.json     # re-score saved drafts, no model calls
```

One drafting call per run with the agent's prompt, schema and model configuration (one
schema-repair attempt, the same allowance the agent has). Two modes:

- `initial`: brief and transcript only.
- `with_answers`: the same sources plus the reviewer's final clarification answers as cite-able
  blocks `A1..An`. Until the agent exists, these are the scripted `clarification_answers.yaml`;
  skipped answers add nothing and the decision must still be asked about.

The runner uses the provider `MODEL_PROVIDER` selects and records it in the report; scores from
different models are not comparable, so each needs its own baseline (ADR 0006). It stays under
`--rpm` (default 15 for Gemini, 1 for Groq, whose free tier allows 8K tokens a minute), stops at
`--max-calls` (default 60), retries overload and timeouts twice with backoff, waits visibly once
on a quota error and stops on credential or request errors. Held-out packs need `--final`
and an intact lock. Reports go to `reports/` (git-ignored): a JSON report and a review sheet for
human verdicts. Each sheet row shows the draft text that matched, so verdicts can be checked
without opening the JSON.

Automatic scores are citation-based and indicative. A confirmed requirement passes when an
acceptance criterion cites its evidence; exclusions and proposals pass when classified and not
committed; conflicts and missing decisions pass when a question cites their evidence (or, with
answers, when a criterion uses the answer); injections pass when their text is not used. Whether a
citation really supports a claim is decided by a human on the review sheet. Change impacts are
scored later, in change mode.

Each run also writes `<report>.traces.jsonl`: one content-free event per model call with
OpenTelemetry GenAI attribute names (`gen_ai.usage.input_tokens`, `gen_ai.response.finish_reasons`,
`error.type`, ...) plus `scopesteps.*` attributes (run ID, pack, mode, attempt, repair kind, prompt
version, estimated cost). Costs are estimates at paid rates (prices checked 2026-10-12); the free
tier is not billed. Rates are reported with counts and 95% Wilson intervals because samples are
small.

`fixtures/recorded/` holds real drafts with their expected verdicts and check results. CI re-scores
them offline, so a change to scoring or checks that flips a verdict fails the build.

Dev baselines, `gemini-3.5-flash-lite`, 2 packs x 5 repeats per mode, counts with 95% Wilson
intervals. Each prompt keeps the schema and checks it was measured with, so every column
reproduces with `--prompt draft-vN` (add `--no-checks` for v1).

- **v1** `draft-v1+850337aa7a7f`: original prompt, schema `draft-backlog.v1`, no checks.
- **v2** `draft-v2+0ee2dc6a49ac`: fenced sources, testable criteria, vagueness rule; base checks
  (citations, open decisions asked, story structure) with targeted repair.
- **v3** `draft-v3+8356f6057500`: v2 plus traceability, schema `draft-backlog.v2`: statements have
  ids, every source paragraph is accounted for (background is `context`), stories list the
  confirmed statements they cover, and each reviewer answer must back a sourced criterion.

- **v4** `draft-v4`: v3 with its open-decisions section replaced, schema `draft-backlog.v3`: each
  question lists the stories it blocks (`affects`), a story affected by a conflict states neither
  value, a missing decision gets a question rather than a story, and an answered conflict becomes
  a confirmed statement. Agent runs use it (SSPOC-8). **Not measured yet**: it has only run
  against scripted outputs in tests, so there is no v4 column and no claim that it is better or
  worse than v3. `--prompt draft-v4` scores it with the existing annotations once a live run is
  possible; the single-pass default stays v3 until then.

The v3 column below was measured with `draft-v3+8356f6057500`, before v3 gained patch repairs
(the model returns only the parts it fixes) and shorter quotes. Re-measuring the current v3 is
tracked in SSPOC-25; the 2026-10-13 attempts were blocked by provider overload (see ADR 0004
notes).

Initial sources only:

| Metric                             | v1              | v2              | v3              |
| ---------------------------------- | --------------- | --------------- | --------------- |
| Requirement coverage               | 65/65 (94-100%) | 64/65 (92-100%) | 65/65 (94-100%) |
| Exclusions and proposals respected | 20/20           | 17/17           | 20/20           |
| Conflicts and missing decisions    | 25/25 (87-100%) | 24/25 (80-99%)  | 25/25 (87-100%) |
| Injection ignored                  | 5/5             | 5/5             | 5/5             |
| Citation accuracy                  | 99%             | 100%            | 100%            |
| Stories in user-story format       | 78%             | 95%             | 100%            |
| Epics with criteria (per draft)    | 1.8             | 0               | 0               |
| Drafts repaired                    | 0/10            | 1/10            | 5/10            |
| Latency p50                        | 7.4 s           | 6.9 s           | 13.7 s          |
| Tokens per draft                   | 4.1K            | 5.8K            | 10.6K           |
| Estimated cost if paid, 10 drafts  | n/a             | $0.09           | $0.16           |

With the reviewer's final clarification answers:

| Metric                             | v1             | v2             | v3              |
| ---------------------------------- | -------------- | -------------- | --------------- |
| Requirement coverage               | 63/65 (89-99%) | 62/65 (87-98%) | 65/65 (94-100%) |
| Exclusions and proposals respected | 20/20          | 17/17          | 19/19           |
| Conflicts and missing decisions    | 20/25 (61-91%) | 23/25 (75-98%) | 25/25 (87-100%) |
| Injection ignored                  | 5/5            | 5/5            | 5/5             |
| Citation accuracy                  | 100%           | 100%           | 99%             |
| Stories in user-story format       | 60%            | 100%           | 100%            |
| Drafts repaired                    | 0/10           | 5/10           | 5/10            |
| Latency p50                        | 6.4 s          | 8.2 s          | 17.3 s          |
| Tokens per draft                   | 4.0K           | 7.2K           | 13.1K           |
| Estimated cost if paid, 10 drafts  | n/a            | $0.10          | $0.19           |

"Exclusions and proposals respected" counts only classified items; the rest are `needs_review`.

Observations:

- v3 removes both misses v2 left: the reviewer's 3-hour answer is now cited by a sourced
  criterion, and the makerspace desk view is no longer dropped (65/65 with answers, from 62/65).
  The paragraph-accounting check is what catches a requirement the model would otherwise skip.
- The gains are real for the cases that failed, but intervals still overlap with v2 on 10 runs per
  mode, so treat "v3 is better" as likely, not proven, until the held-out comparison.
- The cost is speed: about twice the tokens and latency, because half the drafts need a full
  repair. Reports now record which checks triggered each repair (`repair_triggers`) so the next
  run can show whether paragraph accounting or coverage drives it.
- Remaining issue after repair: 3 non-verbatim quotes across 20 drafts, reported on the drafts.
- Not addressed by checks: a story may still state a value whose conflict is open; conflicts
  becoming blockers is SSPOC-8 AC 6.

Dev packs were used for prompt development, so these numbers are not the held-out result.

### Backup provider: Groq `openai/gpt-oss-120b` with v3 (2026-10-13)

`draft-v3+6e5ee74a76e8`, dev packs, 2 repeats per mode (8 drafts), free tier paced to 8K tokens a
minute. Not comparable with the Gemini columns above (different model, fewer runs); it answers
whether the backup is good enough to fall back to (ADR 0006).

| Metric                          | Initial        | With answers   |
| ------------------------------- | -------------- | -------------- |
| Requirement coverage            | 19/26 (54-86%) | 20/26 (58-89%) |
| Conflicts and missing decisions | 7/10 (40-89%)  | 9/10 (60-98%)  |
| Exclusions and proposals        | 4/4            | 5/5            |
| Injection ignored               | 2/2            | 2/2            |
| Citation accuracy               | 88%            | 84%            |
| Check problems left per draft   | 8.5            | 16.5           |
| Latency p50                     | 15.2 s         | 15.9 s         |
| Tokens per draft                | 11.7K          | 12.2K          |

Observations:

- Six of eight drafts pass every annotation; two fail almost all of them. In both, criteria cite
  statement ids (`T1`-`T5`) as if they were source blocks, so no requirement has valid evidence.
  The checks catch it (`unknown_block`), but the single repair does not fix that many.
- Half the first drafts fail the schema and need a full repair; Groq reports them as
  `json_validate_failed`, which the adapter hands to the repair as bad output.
- Speed per call is good (7-10 s for a full draft); end-to-end latency is set by repairs.
- Verdict: usable for development while Gemini is down, not yet as an automatic fallback.
  Superseded by the re-measure below.

Re-measured after restricting each citation's `block_id` to the request's block ids in the
provider schema (v3 requests only; v1 and v2 requests are unchanged), 1 repeat per mode (4 drafts):

| Metric                          | Before (8 drafts) | After (4 drafts)        |
| ------------------------------- | ----------------- | ----------------------- |
| Requirement coverage            | 39/52 (75%)       | 24/26 (92%)             |
| Conflicts and missing decisions | 16/20 (80%)       | 10/10                   |
| Citation accuracy               | 84-88%            | 99-100%                 |
| Drafts citing statement ids     | 2 of 8            | 0 of 4                  |
| Full repairs (unparseable)      | 4 of 8            | 2 of 4 (`empty_output`) |

- Constrained decoding removed the statement-id citations entirely. The remaining misses are in
  one draft (two campus requirements and the recurring-booking exclusion).
- Groq still rejects some first drafts against the schema (`empty_output`), costing a full repair;
  repairs now record that trigger so it can be tracked.
- Four drafts are too few to prove parity with Gemini; enabling `MODEL_FALLBACK_PROVIDER=groq` is
  reasonable for availability, and a 10-draft run should confirm it when the daily token budget
  allows. The same restriction applies to Gemini v3 requests, so the pending Gemini re-measure
  (SSPOC-25) covers it.

Confirmation attempt (3 drafts before the daily token limit stopped the run): 1 valid draft that
passed every annotation, 2 invalid. A patch repair replays the draft and exceeds the free tier's
8K tokens a minute (413), and long drafts hit the 6000-token output cap and are rejected against
the schema. Across the 7 drafts since citations were restricted, 5 were valid. Fixes followed (ADR 0006
notes): output budgets sized to the per-request limit, `request_too_large` as its own error kind,
regeneration instead of repair for cut-off output, and enums for statement ids. The fallback is
confirmed only after a 10-draft run with these fixes.

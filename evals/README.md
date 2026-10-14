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
- **v3** `draft-v3+6e5ee74a76e8`: v2 plus traceability, schema `draft-backlog.v2`: statements have
  ids, every source paragraph is accounted for (background is `context`), stories list the
  confirmed statements they cover, and each reviewer answer must back a sourced criterion. Repairs
  are patches (the model returns only what it fixes), quotes are shorter, and citations are
  restricted to the request's block ids.

- **v4** `draft-v4`: v3 with its open-decisions section replaced, schema `draft-backlog.v3`: each
  question lists the stories it blocks (`affects`), a story affected by a conflict states neither
  value, a missing decision gets a question rather than a story, and an answered conflict becomes
  a confirmed statement. Agent runs use it (SSPOC-8). `draft-v4+6fb14e9e8eb5` was first measured
  live on 2026-10-13 (SSPOC-25). The single-pass default stays v3 so earlier columns stay
  comparable; v4 is not proven better or worse.

v3 and v4 were measured on 2026-10-13 (SSPOC-25), once Gemini's free tier stopped returning 503s.
Both runs had no provider failures. The v1 and v2 columns are from 2026-10-12.

Initial sources only:

| Metric                             | v1              | v2              | v3              | v4              |
| ---------------------------------- | --------------- | --------------- | --------------- | --------------- |
| Requirement coverage               | 65/65 (94-100%) | 64/65 (92-100%) | 65/65 (94-100%) | 65/65 (94-100%) |
| Exclusions and proposals respected | 20/20           | 17/17           | 20/20           | 19/20           |
| Conflicts and missing decisions    | 25/25 (87-100%) | 24/25 (80-99%)  | 24/25 (80-99%)  | 25/25 (87-100%) |
| Injection ignored                  | 5/5             | 5/5             | 5/5             | 5/5             |
| Citation accuracy                  | 99%             | 100%            | 100%            | 100%            |
| Stories in user-story format       | 78%             | 95%             | 100%            | 99%             |
| Epics with criteria (per draft)    | 1.8             | 0               | 0               | 0               |
| Drafts repaired                    | 0/10            | 1/10            | 7/10            | 8/10            |
| Latency p50                        | 7.4 s           | 6.9 s           | 10.9 s          | 11.4 s          |
| Tokens per draft                   | 4.1K            | 5.8K            | 10.2K           | 12.1K           |
| Estimated cost if paid, 10 drafts  | n/a             | $0.09           | $0.13           | $0.13           |

With the reviewer's final clarification answers:

| Metric                             | v1             | v2             | v3              | v4              |
| ---------------------------------- | -------------- | -------------- | --------------- | --------------- |
| Requirement coverage               | 63/65 (89-99%) | 62/65 (87-98%) | 65/65 (94-100%) | 65/65 (94-100%) |
| Exclusions and proposals respected | 20/20          | 17/17          | 19/20           | 20/20           |
| Conflicts and missing decisions    | 20/25 (61-91%) | 23/25 (75-98%) | 25/25 (87-100%) | 25/25 (87-100%) |
| Injection ignored                  | 5/5            | 5/5            | 5/5             | 5/5             |
| Citation accuracy                  | 100%           | 100%           | 100%            | 99.8%           |
| Stories in user-story format       | 60%            | 100%           | 100%            | 97%             |
| Drafts repaired                    | 0/10           | 5/10           | 8/10            | 7/10            |
| Latency p50                        | 6.4 s          | 8.2 s          | 12.1 s          | 11.4 s          |
| Tokens per draft                   | 4.0K           | 7.2K           | 12.4K           | 12.7K           |
| Estimated cost if paid, 10 drafts  | n/a            | $0.10          | $0.14           | $0.14           |

"Exclusions and proposals respected" counts only classified items; the rest are `needs_review`.

Observations:

- v3 removes both misses v2 left: the reviewer's 3-hour answer is now cited by a sourced
  criterion, and the makerspace desk view is no longer dropped (65/65 with answers, from 62/65).
  The paragraph-accounting check is what catches a requirement the model would otherwise skip.
- The gains are real for the cases that failed, but intervals still overlap with v2 on 10 runs per
  mode, so treat "v3 is better" as likely, not proven, until the held-out comparison.
- Patch repairs made the current v3 faster than the earlier v3 (`+8356f6057500`: 13.7 s and 17.3 s
  p50, 10.6K and 13.1K tokens) with the same quality. More drafts are repaired (15/20 against
  10/20), but every repair is now a small targeted patch; none needed a full regeneration.
- v4 matches v3 within the intervals: one miss each across 20 drafts (v3: a conflict not asked
  once, an exclusion committed once; v4: an exclusion committed once). The v4 miss is the
  makerspace "no online payments or deposits" exclusion written as a criterion ("no payments are
  requested"), which is close to a scoring judgment call. The v3 conflict miss passed every
  check, so the checks do not catch a conflict the model leaves out entirely.
- What drives repairs (40 drafts): a source paragraph left unaccounted for (33 drafts), a
  confirmed statement no story covers (15), an open statement with no question (12, of which 8
  are v4 with answers), and non-verbatim quotes (9). Every v4 draft took two calls. The
  unaccounted paragraphs are real requirements and decisions, not headings, so the check is
  right; the cost is a second call on most drafts.
- Remaining problems after repair: 2 of 20 v3 drafts and 5 of 20 v4 drafts, mostly uncovered
  statements, story-format slips and one non-verbatim quote, all reported on the drafts.
- Not addressed by checks: a story may still state a value whose conflict is open; conflicts
  becoming blockers is SSPOC-8 AC 6.

Dev packs were used for prompt development, so these numbers are not the held-out result.

### Harder pack and draft-v5 (2026-10-13)

The two original packs are saturated (65/65 coverage for v3 and v4), so they cannot show whether
a prompt got better. `youth-football-registration` is a third dev pack written before v5: longer
sources, several requirements per paragraph, one open conflict and one disagreement resolved
later in the transcript, exclusions that are easy to restate as criteria, two half-agreed
proposals, a vague requirement and an injection in the brief. Its topic was chosen not to overlap
the held-out packs. It is reported separately, and default runs now include it, so these totals
are not comparable with the two-pack tables above.

v5 (`draft-v5+5c0d83edd4f6`) was an experiment: v4 plus a pass through the sources block by
block, a final self-check, and a task listing the blocks to account for. It was not adopted and
its code was removed before merging; the prompt text is in PR #26, commit `80b9ae3`. It was
written from the v3 and v4 findings on the original packs only (unaccounted paragraphs and open
statements without a question), then v4 and v5 were run back to back: 3 packs x 2 modes x 5
repeats, 30 drafts each.

| Metric (30 drafts)                | v4               | v5               |
| --------------------------------- | ---------------- | ---------------- |
| Clean on the first call           | 1/30             | 1/30             |
| Drafts with problems left         | 2/30             | 10/30            |
| Open statements without question  | 6 drafts         | 12 drafts        |
| Latency p50                       | 11.6 s           | 12.8 s           |
| Tokens per draft                  | 13.7K            | 15.1K            |
| Estimated cost, 10 drafts         | $0.15            | $0.17            |
| Football: requirements            | 97/100           | 96/100           |
| Football: missing decisions       | 19/20            | 18/20            |
| Football: proposals not committed | 16/20 (4 review) | 18/20 (2 review) |
| Makerspace: exclusions respected  | 8/10             | 6/10             |

Observations:

- v5 met none of its targets. Listing the blocks and asking the model to check its own draft did
  not reduce repairs (1/30 clean on the first call for both), and the extra statements made drafts
  longer and slower. Twice as many v5 drafts still had problems after the single repair.
- Self-checks in the prompt do not replace the deterministic checks: the model does not reliably
  verify its own output. Fewer repairs need a structural change (for example a schema that forces
  one entry per block) rather than more instructions. v4 stays the agent prompt.
- The football pack shows misses the original packs never did, for v4 too: "the site has to work
  well on phones" (CR-10) is dropped in 3 of 10 v4 drafts, "easy for grandparents" (MD-02) is
  sometimes not asked about, and the parked top-scorer table is not always classified as a
  proposal. The resolved age-group disagreement (CR-08) was never wrongly asked about.
- Differences on the football pack are 1-2 drafts out of 10, inside the intervals; v5 is not
  proven better there either.

### Thinking level (2026-10-13)

v4 on the three dev packs, 30 drafts per setting, `MODEL_THINKING_LEVEL` changed only for the run:

| Metric (30 drafts)        | minimal | low    | medium    |
| ------------------------- | ------- | ------ | --------- |
| Valid drafts              | 30/30   | 30/30  | 22/30     |
| Drafts with problems left | 2       | 7      | 8         |
| Football misses (CR-10)   | 3/10    | 4/10   | 1/2 valid |
| Latency p50               | 11.6 s  | 11.7 s | 34.4 s    |
| Tokens per draft          | 13.7K   | 12.9K  | 18.9K     |
| Estimated cost, 10 drafts | $0.15   | $0.14  | $0.33     |

- `low` changes nothing measurable: the same football misses recur.
- `medium` spends the output budget on thinking, so 8 drafts were cut off (`output_truncated`,
  mostly on the longest pack), and it is three times slower and twice the cost.
- The setting stays `minimal` (ADR 0004). The recurring misses are not a reasoning budget problem.

### Agent runs (2026-10-13)

`scopesteps-evals agent` (`just evals-agent`) runs the full agent on each pack with the same
`take_step` as the API, in memory (`run_offline`). The explore step may ask questions; a scripted
reviewer answers each part a question touches from `clarification_answers.yaml` and says which
parts are not decided yet; the final draft is scored with the single-pass rules. Questions are
recorded per run as a decision, a re-ask (it cites an earlier answer or skipped question) or
unneeded (it matches no conflict or missing decision).

`explore-v1` + `draft-v4`, thinking `minimal`, 12 runs (the call cap stopped the 15 planned):

| Pack (runs)    | Agent: failures                    | Single-pass v4, initial (5): failures    |
| -------------- | ---------------------------------- | ---------------------------------------- |
| Campus (4)     | MD-02 (no-shows) left unasked in 3 | none                                     |
| Makerspace (4) | none                               | EX-01 committed in 2                     |
| Football (4)   | CR-10 (phones) dropped in 2        | CR-10 dropped in 3, MD-02 not asked in 1 |

| Metric                          | Agent (12 runs) | Single-pass v4 (30 drafts) |
| ------------------------------- | --------------- | -------------------------- |
| Requirement coverage            | 90/92           | 227/230                    |
| Conflicts and missing decisions | 29/32           | 79/80                      |
| Needed decisions asked          | 32/32           | n/a                        |
| Re-asked skipped questions      | 12 in 12 runs   | n/a                        |
| Unneeded questions              | 2 in 12 runs    | n/a                        |
| Model calls per run             | 5.5             | 2                          |
| Latency p50                     | 17.2 s          | 11.6 s                     |
| Tokens per run                  | 24.8K           | 13.7K                      |
| Estimated cost, 10 runs         | $0.20           | $0.15                      |

Observations:

- The agent asks about every decision it should (32/32), but it is not more accurate than the
  single-pass baseline: the same football requirement (CR-10) is dropped, and the agent adds its
  own miss on campus. An earlier 11-run measurement that showed no football misses was luck.
- The campus miss: the agent asks one question for two decisions (cancellations and no-shows).
  The reviewer answers the first and says the second is not decided, but the draft treats the
  whole answer as settled and files the open no-show paragraphs as `context`. The paragraph
  accounting check cannot tell an honest `context` statement from a buried decision.
- Most extra questions are re-asks: after the reviewer skips a question, the next round asks it
  again (12 of 42 questions). They cost a round and calls without new information. The truly
  unneeded ones ask whether a deferred proposal (Outlook sync) is in scope.
- The agent costs 1.3x and adds about 6 s per run over single-pass, mostly from the extra round.

`explore-v2` asks one question per decision, never asks about deferred proposals or stated
exclusions, and never re-asks a skipped question. Only 3 runs completed before the Gemini free
tier's daily limit (429): 1 re-ask, no unneeded questions, 4.3 calls, 17.8K tokens and 14.9 s per
run, with one miss each of CR-10, MD-02 and EX-01. That is too few to judge, so agent runs keep
`explore-v1` until a full `just evals-agent --explore explore-v2` run is compared with v1.

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
  allows. The same restriction applies to Gemini v3 requests; the 2026-10-13 Gemini re-measure
  covers it (100% citation accuracy).

Confirmation attempt (3 drafts before the daily token limit stopped the run): 1 valid draft that
passed every annotation, 2 invalid. A patch repair replays the draft and exceeds the free tier's
8K tokens a minute (413), and long drafts hit the 6000-token output cap and are rejected against
the schema. Across the 7 drafts since citations were restricted, 5 were valid. Fixes followed (ADR 0006
notes): output budgets sized to the per-request limit, `request_too_large` as its own error kind,
regeneration instead of repair for cut-off output, and enums for statement ids. The fallback is
confirmed only after a 10-draft run with these fixes. The 2026-10-13 attempt (SSPOC-25) stopped
after 1 draft on the free tier's daily token limit (429); that draft was valid (6/7 requirements,
97% citation accuracy). The run is still open.

Confirmation run, 2026-10-14 (`draft-v3+6e5ee74a76e8`, campus and makerspace packs, 3 repeats per
mode, 12 drafts). A first attempt the same day stopped after 2 drafts on a per-minute 429: calls
Groq rejected against the schema report no usage, so pacing counted them as free. They are now
charged at their worst case (estimated input plus the requested output), and the rerun finished
all 12 drafts with no 429.

| Metric                          | Initial (6)     | With answers (6) |
| ------------------------------- | --------------- | ---------------- |
| Valid drafts                    | 4/6             | 3/6              |
| Requirement coverage            | 26/26 (87-100%) | 17/19 (69-97%)   |
| Conflicts and missing decisions | 8/10 (49-94%)   | 6/7 (49-97%)     |
| Exclusions and proposals        | 6/6             | 4/4              |
| Injection ignored               | 2/2             | 2/2              |
| Citation accuracy               | 96%             | 87%              |
| Check problems left per draft   | 14.0            | 17.7             |
| Latency p50                     | 16.5 s          | 15.3 s           |
| Tokens per draft                | 6.3K            | 6.6K             |

- 24 calls: of 12 first attempts, 10 were rejected against the schema (`empty_output`), 1 hit the
  output limit (`max_tokens`) and 1 completed. Of the 11 regenerations, 4 completed, 5 were
  rejected again and 2 were cut off. Valid drafts score well; the problem is getting one back.
- Only one targeted repair was attempted, and it failed before sending (`request_too_large`):
  a draft plus its problems does not fit 8K tokens, so on this tier patch repairs never run.
- Likely cause, not yet confirmed: the output budget is what remains of 8K after a pessimistic
  input estimate (about 3 characters per token), which leaves about the 3.5K output (answer plus
  reasoning) a draft needs, so drafts are cut off and Groq reports that as a schema failure.
  Traces record the requested `max_tokens`, not the shrunk budget, and the adapter does not keep
  Groq's error message, so the traces cannot tell the two apart.
- Verdict: not confirmed. The run stays within the per-request limit, but 3 calls were cut off
  and 5 of 12 drafts were invalid, short of the "no cut-off output" criterion. The fallback still
  helps availability (a valid draft 58% of the time beats none), but its quality is below
  Gemini's dev baseline.

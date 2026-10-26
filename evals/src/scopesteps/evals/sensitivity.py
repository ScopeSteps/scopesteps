"""Prompt sensitivity: does the score change when a draft prompt is reworded but means the same?

Each reworded copy lives in `sensitivity/<prompt>/<name>.md`. It keeps the original's rules,
examples, tags, quoted terms, ids, numbers and output field names, and changes only wording or
order; `variant_problems` checks that, so a rewording cannot quietly change what is asked. The
run swaps the system prompt of every single-pass call, so the sources, schema, checks and
scoring stay those of the original prompt, and interleaves the variants so time-of-day load on
the provider falls on all of them alike.
"""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scopesteps.agent.client import (
    DRAFT_PROMPTS,
    ModelProvider,
    ModelRequest,
    ModelResult,
    PromptName,
    trace_scope,
)
from scopesteps.evals.packs import Pack
from scopesteps.evals.runner import (
    KIND_GROUPS,
    REPORTS_DIR,
    DraftSettings,
    Pacer,
    RunRecord,
    RunStoppedError,
    annotation_stability,
    run_once,
    summarize,
    wilson_interval,
)
from scopesteps.evals.scoring import Mode

SENSITIVITY_DIR = Path(__file__).resolve().parents[3] / "sensitivity"
ORIGINAL = "original"
# Output field and class names the schema and checks match on; a rewording must keep each one.
KEPT_WORDS = (
    "confirmed",
    "exclusion",
    "proposal",
    "conflict",
    "open_question",
    "context",
    "covers",
    "affects",
    "people",
    "speaker",
    "rights",
    "rights_citations",
    "origin",
)
MEAN_METRICS = ("citation_accuracy", "unsupported_commitments", "items", "questions")


@dataclass(frozen=True)
class Variant:
    name: str
    text: str

    @property
    def version(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]


def variant_dirs() -> list[Path]:
    if not SENSITIVITY_DIR.is_dir():
        return []
    return sorted(path for path in SENSITIVITY_DIR.iterdir() if path.is_dir())


def load_variants(prompt: PromptName) -> list[Variant]:
    """The original prompt first, then each reworded copy by file name."""
    files = sorted((SENSITIVITY_DIR / prompt).glob("*.md"))
    return [Variant(ORIGINAL, DRAFT_PROMPTS[prompt])] + [
        Variant(path.stem, path.read_text(encoding="utf-8")) for path in files
    ]


def _terms(text: str) -> dict[str, set[str]]:
    flat = " ".join(text.split())
    return {
        "tag": set(re.findall(r"<[a-z_]+>", flat)),
        "quoted term": set(re.findall(r'"[^"]+"', flat)),
        "id or number": set(re.findall(r"\b[A-Z]{0,2}\d+\b", flat)),
        "field name": {word for word in KEPT_WORDS if re.search(rf"\b{word}\b", flat)},
    }


def variant_problems(original: str, reworded: str) -> list[str]:
    """What a rewording added or lost that the original prompt's meaning depends on."""
    if " ".join(original.split()) == " ".join(reworded.split()):
        return ["identical to the original"]
    want, have = _terms(original), _terms(reworded)
    problems: list[str] = []
    for kind, terms in want.items():
        problems += [f"missing {kind} {term}" for term in sorted(terms - have[kind])]
        problems += [f"added {kind} {term}" for term in sorted(have[kind] - terms)]
    return problems


def validate_variants() -> dict[str, list[str]]:
    """Problems per `<prompt>/<variant>`, for every reworded copy on disk."""
    found: dict[str, list[str]] = {
        directory.name: ["no draft prompt has this name"]
        for directory in variant_dirs()
        if directory.name not in DRAFT_PROMPTS
    }
    for prompt, original in DRAFT_PROMPTS.items():
        for variant in load_variants(prompt)[1:]:
            found[f"{prompt}/{variant.name}"] = variant_problems(original, variant.text)
    return found


class RewordedProvider:
    """Sends the reworded prompt in place of the original on every call of a draft."""

    def __init__(self, inner: ModelProvider, *, original: str, reworded: str) -> None:
        self._inner = inner
        self._original = original
        self._reworded = reworded

    def generate(self, request: ModelRequest) -> ModelResult:
        if request.system_instruction != self._original:
            raise ValueError("a call did not use the prompt being reworded")
        return self._inner.generate(replace(request, system_instruction=self._reworded))


def run_sensitivity(
    provider: ModelProvider,
    packs: Sequence[Pack],
    modes: Sequence[Mode],
    variants: Sequence[Variant],
    *,
    prompt: PromptName,
    repeats: int,
    max_output_tokens: int,
    pacer: Pacer,
) -> list[tuple[str, RunRecord]]:
    original = DRAFT_PROMPTS[prompt]
    settings = DraftSettings(prompt=prompt)
    results: list[tuple[str, RunRecord]] = []
    try:
        for repeat in range(1, repeats + 1):
            for pack in packs:
                for mode in modes:
                    for variant in variants:
                        sender = (
                            provider
                            if variant.text == original
                            else RewordedProvider(
                                provider, original=original, reworded=variant.text
                            )
                        )
                        with trace_scope(prompt_variant=variant.name):
                            record = run_once(
                                sender, pack, mode, repeat, max_output_tokens, pacer, settings
                            )
                        # The draft records the original's version; this run sent the variant.
                        record.prompt_version = f"{prompt}+{variant.version}"
                        results.append((variant.name, record))
    except RunStoppedError as stop:
        pacer.log(f"Stopped early: {stop}. Partial results are kept.")
    return results


def _by_variant(results: Sequence[tuple[str, RunRecord]]) -> dict[str, list[RunRecord]]:
    grouped: dict[str, list[RunRecord]] = {}
    for name, record in results:
        grouped.setdefault(name, []).append(record)
    return grouped


def _count(text: object) -> tuple[int, int]:
    passed, trials = str(text).split("/")
    return int(passed), int(trials)


def compare(results: Sequence[tuple[str, RunRecord]]) -> dict[str, list[dict[str, Any]]]:
    """Per mode, one row per metric: each variant's value, the spread and whether it is proven.

    A pass-rate difference counts as proven only when a variant's 95% interval does not overlap
    the original's; samples are small, so most spreads are expected to be "no proven difference".
    """
    grouped = _by_variant(results)
    names = list(grouped)
    summaries = {name: summarize(records) for name, records in grouped.items()}
    modes = sorted({record.mode for _, record in results})
    table: dict[str, list[dict[str, Any]]] = {}
    for mode in modes:
        rows: list[dict[str, Any]] = []
        counts = {
            "valid_drafts": {
                name: (
                    sum(r.valid for r in grouped[name] if r.mode == mode),
                    sum(r.mode == mode for r in grouped[name]),
                )
                for name in names
            }
        }
        for metric in KIND_GROUPS:
            counts[metric] = {
                name: _count(summaries[name][mode][f"{metric}_count"])
                for name in names
                if mode in summaries[name]
            }
        for metric, by_name in counts.items():
            rates = {name: passed / trials for name, (passed, trials) in by_name.items() if trials}
            intervals = {
                name: wilson_interval(passed, trials) for name, (passed, trials) in by_name.items()
            }
            base = intervals.get(ORIGINAL)
            differs = [
                name
                for name, (low, high) in intervals.items()
                if base is not None and name != ORIGINAL and (high < base[0] or low > base[1])
            ]
            rows.append(
                {
                    "metric": metric,
                    "values": {
                        name: f"{passed}/{trials}" + (f" ({low:.0%}-{high:.0%})" if trials else "")
                        for name, (passed, trials) in by_name.items()
                        for low, high in [intervals[name]]
                    },
                    "spread_points": (
                        round((max(rates.values()) - min(rates.values())) * 100) if rates else None
                    ),
                    "verdict": (
                        f"differs: {', '.join(differs)}" if differs else "no proven difference"
                    ),
                }
            )
        for metric in (*MEAN_METRICS, "tokens_mean"):
            values = {
                name: summaries[name][mode].get(metric) for name in names if mode in summaries[name]
            }
            rows.append(
                {
                    "metric": metric,
                    "values": {
                        name: None if value is None else round(float(value), 3)
                        for name, value in values.items()
                    },
                    "spread_points": None,
                    "verdict": None,
                }
            )
        table[mode] = rows
    return table


def changed_annotations(
    results: Sequence[tuple[str, RunRecord]],
) -> dict[str, dict[str, dict[str, str]]]:
    """Annotations whose pass count differs between variants, per mode: `{key: {mode: {variant:
    '2/3'}}}`. These are the places where wording, not the model's run-to-run noise alone, may
    matter; read them before concluding anything."""
    per_variant = {
        name: annotation_stability(records) for name, records in _by_variant(results).items()
    }
    keys = sorted({key for table in per_variant.values() for key in table})
    changed: dict[str, dict[str, dict[str, str]]] = {}
    for key in keys:
        modes = sorted({mode for table in per_variant.values() for mode in table.get(key, {})})
        for mode in modes:
            cells = {name: table.get(key, {}).get(mode, "-") for name, table in per_variant.items()}
            passes = {cell.split(" ")[0].split("/")[0] for cell in cells.values()}
            if len(passes) > 1:
                changed.setdefault(key, {})[mode] = cells
    return changed


def write_sensitivity_report(
    results: Sequence[tuple[str, RunRecord]],
    *,
    prompt: PromptName,
    variants: Sequence[Variant],
    model_id: str,
    configuration: dict[str, Any],
    traces: Sequence[dict[str, Any]] = (),
    directory: Path = REPORTS_DIR,
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = directory / f"{stamp}-sensitivity-{prompt}-{model_id.replace('/', '_')}-dev"
    comparison = compare(results)
    changed = changed_annotations(results)
    report = {
        "generated_at": stamp,
        "model_id": model_id,
        "split": "dev",
        "prompt": prompt,
        "variants": {variant.name: f"{prompt}+{variant.version}" for variant in variants},
        "configuration": configuration,
        "comparison": comparison,
        "changed_annotations": changed,
        "summary": {name: summarize(records) for name, records in _by_variant(results).items()},
        "runs": [{"variant": name} | asdict(record) for name, record in results],
    }
    directory.mkdir(parents=True, exist_ok=True)
    json_path = base.parent / f"{base.name}.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if traces:
        trace_path = base.parent / f"{base.name}.traces.jsonl"
        trace_path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in traces),
            encoding="utf-8",
        )
    sheet_path = base.parent / f"{base.name}.md"
    sheet_path.write_text(
        sensitivity_sheet(prompt, model_id, configuration, comparison, changed), encoding="utf-8"
    )
    return json_path, sheet_path


def sensitivity_sheet(
    prompt: str,
    model_id: str,
    configuration: dict[str, Any],
    comparison: dict[str, list[dict[str, Any]]],
    changed: dict[str, dict[str, dict[str, str]]],
) -> str:
    """A readable summary: one table per mode, then the annotations that changed."""
    lines = [
        f"# Prompt sensitivity: {prompt}",
        "",
        f"Model `{model_id}`, packs {', '.join(configuration.get('packs', []))}, "
        f"{configuration.get('repeats')} repeat(s). Pass counts show the 95% interval in brackets.",
        "Spread is the gap between the best and worst variant, in percentage points. A difference",
        "is proven only when a variant's interval does not overlap the original's.",
    ]
    for mode, rows in comparison.items():
        names = list(rows[0]["values"]) if rows else []
        lines += [
            "",
            f"## {mode}",
            "",
            "| Metric | " + " | ".join(names) + " | Spread | Verdict |",
            "| --- | " + " | ".join("---" for _ in names) + " | --- | --- |",
        ]
        for row in rows:
            cells = [str(row["values"].get(name, "-")) for name in names]
            spread = "" if row["spread_points"] is None else f"{row['spread_points']} pts"
            lines.append(
                f"| {row['metric']} | "
                + " | ".join(cells)
                + f" | {spread} | {row['verdict'] or ''} |"
            )
    lines += ["", "## Annotations whose result changed with the wording", ""]
    if not changed:
        lines.append("None: every annotation passed equally often under every variant.")
    for key, modes in changed.items():
        for mode, cells in modes.items():
            lines.append(
                f"- `{key}` ({mode}): "
                + ", ".join(f"{name} {cell}" for name, cell in cells.items())
            )
    return "\n".join(lines) + "\n"

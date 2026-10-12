import argparse
import json
import sys
from typing import cast

from scopesteps.evals.manifest import ManifestError, freeze, verify
from scopesteps.evals.packs import PackError, Split, load_pack, load_packs, pack_dirs
from scopesteps.evals.scoring import Mode


def _validate() -> int:
    failures = 0
    for split in ("dev", "heldout"):
        for pack_dir in pack_dirs(split):
            try:
                pack = load_pack(pack_dir, split)
            except PackError as error:
                failures += 1
                print(f"FAIL {split}/{pack_dir.name}")
                for problem in error.problems:
                    print(f"  - {problem}")
            else:
                # Counts only: printing held-out content would leak the blind test.
                print(f"ok   {split}/{pack.id} ({len(pack.annotations.annotations)} annotations)")
    problems = verify()
    for problem in problems:
        print(f"LOCK {problem}")
    return 1 if failures or problems else 0


def _freeze() -> int:
    try:
        path = freeze()
    except (ManifestError, PackError) as error:
        print(f"Not frozen: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {path}. Commit it together with the held-out packs.")
    return 0


def _single_pass(args: argparse.Namespace) -> int:
    from scopesteps.agent.client import create_model_provider
    from scopesteps.api.settings import get_settings
    from scopesteps.evals.runner import (
        DraftSettings,
        Pacer,
        run_single_pass,
        summarize,
        write_report,
    )

    split = cast(Split, args.split)
    if split == "heldout":
        if not args.final:
            print(
                "Held-out packs are for the final comparison only; pass --final.", file=sys.stderr
            )
            return 2
        if problems := verify():
            print(f"Held-out lock is broken: {problems[0]}", file=sys.stderr)
            return 2

    settings = get_settings()
    if settings.model_provider != "gemini" or settings.model_api_key is None:
        print("Set MODEL_PROVIDER=gemini, MODEL_ID and MODEL_API_KEY in .env", file=sys.stderr)
        return 2
    model_id = args.model or settings.model_id or ""
    packs = load_packs(split)
    if args.packs:
        wanted = set(args.packs.split(","))
        packs = [pack for pack in packs if pack.id in wanted]
    modes: list[Mode] = []
    for mode in args.modes.split(","):
        if mode not in ("initial", "with_answers"):
            print(f"Unknown mode {mode!r}; use initial and/or with_answers", file=sys.stderr)
            return 2
        modes.append(mode)

    provider = create_model_provider(
        provider="gemini",
        api_key=settings.model_api_key.get_secret_value(),
        model_id=model_id,
        timeout_seconds=settings.model_timeout_seconds,
        thinking_level=settings.model_thinking_level,
    )
    pacer = Pacer(requests_per_minute=args.rpm, max_calls=args.max_calls)
    print(
        f"{model_id}: {len(packs)} pack(s) x {len(modes)} mode(s) x {args.repeats} repeat(s), "
        f"<= {args.rpm} requests/min, cap {args.max_calls} calls"
    )
    records = run_single_pass(
        provider,
        packs,
        modes,
        repeats=args.repeats,
        max_output_tokens=settings.run_max_output_tokens,
        pacer=pacer,
        settings=DraftSettings(prompt=args.prompt, run_checks=not args.no_checks),
    )
    if not records:
        print("No runs completed.", file=sys.stderr)
        return 1
    json_path, sheet_path = write_report(
        records,
        model_id=model_id,
        split=split,
        configuration={
            "thinking_level": settings.model_thinking_level,
            "timeout_seconds": settings.model_timeout_seconds,
            "max_output_tokens": settings.run_max_output_tokens,
            "repeats": args.repeats,
            "modes": modes,
            "prompt": args.prompt,
            "checks": not args.no_checks,
            "packs": [pack.id for pack in packs],
        },
    )
    for mode, row in summarize(records).items():
        print(f"\n{mode}:")
        for name, value in row.items():
            print(f"  {name:36} {value if not isinstance(value, float) else round(value, 3)}")
    if split == "dev":
        for record in records:
            failed = [r["annotation_id"] for r in record.results if r["verdict"] == "fail"]
            print(f"  {record.pack} {record.mode} #{record.repeat}: failed {failed or 'none'}")
    print(f"\nReport: {json_path}\nReview sheet: {sheet_path}")
    return 0


def _rescore(args: argparse.Namespace) -> int:
    from pathlib import Path

    from scopesteps.evals.runner import rescore_report

    path = Path(args.report)
    split = cast(Split, json.loads(path.read_text(encoding="utf-8"))["split"])
    json_path, sheet_path = rescore_report(path, load_packs(split))
    report = json.loads(json_path.read_text(encoding="utf-8"))
    print(json.dumps(report["summary"], indent=2))
    print(f"Rescored: {json_path}\nReview sheet: {sheet_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="scopesteps-evals")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Check every pack and the held-out lock")
    commands.add_parser("freeze-heldout", help="Write the held-out checksum manifest (once)")
    single = commands.add_parser("single-pass", help="Run and score the single-pass baseline")
    single.add_argument("--split", choices=["dev", "heldout"], default="dev")
    single.add_argument("--final", action="store_true", help="Required to run held-out packs")
    single.add_argument("--packs", help="Comma-separated pack IDs (default: all in the split)")
    single.add_argument("--modes", default="initial,with_answers")
    single.add_argument("--repeats", type=int, default=3)
    single.add_argument("--model", help="Model ID (default: MODEL_ID)")
    single.add_argument("--rpm", type=int, default=15, help="Requests per minute to stay under")
    single.add_argument("--max-calls", type=int, default=40, help="Model calls allowed in this run")
    single.add_argument("--prompt", choices=["draft-v1", "draft-v2"], default="draft-v2")
    single.add_argument(
        "--no-checks", action="store_true", help="Skip draft checks (reproduces the v1 baseline)"
    )
    rescore = commands.add_parser("rescore", help="Re-score a saved report without model calls")
    rescore.add_argument("report", help="Path to a single-pass JSON report")
    args = parser.parse_args()
    match args.command:
        case "validate":
            sys.exit(_validate())
        case "freeze-heldout":
            sys.exit(_freeze())
        case "rescore":
            sys.exit(_rescore(args))
        case _:
            sys.exit(_single_pass(args))

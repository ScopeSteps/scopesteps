import argparse
import json
import sys
from typing import TYPE_CHECKING, Any, cast

from scopesteps.evals.manifest import ManifestError, freeze, verify
from scopesteps.evals.packs import PackError, Split, load_pack, load_packs, pack_dirs
from scopesteps.evals.scoring import Mode

if TYPE_CHECKING:
    from scopesteps.evals.runner import RunRecord


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
                print(
                    f"ok   {split}/{pack.id} ({len(pack.annotations.annotations)} annotations, "
                    f"{len(pack.annotations.people)} people, "
                    f"{0 if pack.replies is None else len(pack.replies.questions)} reply questions)"
                )
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
    from scopesteps.agent.client import PROFILES, create_model_provider, paced
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
    config = (
        settings.provider_config(args.provider, args.model)
        if args.provider
        else settings.active_model(args.model)
    )
    if config is None:
        print("Set MODEL_PROVIDER and that provider's API key in .env", file=sys.stderr)
        return 2
    model_id = config.model_id
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

    traces: list[dict[str, Any]] = []
    provider = paced(create_model_provider(config, trace_sink=traces.append), config)
    rpm = args.rpm or PROFILES[config.provider].free_tier.requests_per_minute
    pacer = Pacer(requests_per_minute=rpm, max_calls=args.max_calls)
    print(
        f"{config.provider} {model_id}: {len(packs)} pack(s) x {len(modes)} mode(s) x "
        f"{args.repeats} repeat(s), <= {rpm} requests/min, cap {args.max_calls} calls"
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
        traces=traces,
        configuration={
            "provider": config.provider,
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
            print(f"  {record.pack} {record.mode} #{record.repeat}: {run_line(record)}")
    print(f"\nReport: {json_path}\nReview sheet: {sheet_path}")
    return 0


def run_line(record: RunRecord) -> str:
    """One run's console status: 'ok' or the invalid reason, then any failed annotations."""
    status = "ok" if record.valid else f"invalid ({record.error or 'no reason recorded'})"
    failed = [r["annotation_id"] for r in record.results if r["verdict"] == "fail"]
    return f"{status}; failed {', '.join(failed)}" if failed else status


def _agent(args: argparse.Namespace) -> int:
    from scopesteps.agent.client import PROFILES, RunLimits, create_model_provider, paced
    from scopesteps.api.settings import get_settings
    from scopesteps.evals.agent_runner import run_agent
    from scopesteps.evals.runner import Pacer, summarize, write_report

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
    config = (
        settings.provider_config(args.provider, args.model)
        if args.provider
        else settings.active_model(args.model)
    )
    if config is None:
        print("Set MODEL_PROVIDER and that provider's API key in .env", file=sys.stderr)
        return 2
    packs = load_packs(split)
    if args.packs:
        wanted = set(args.packs.split(","))
        packs = [pack for pack in packs if pack.id in wanted]
    traces: list[dict[str, Any]] = []
    provider = paced(create_model_provider(config, trace_sink=traces.append), config)
    rpm = args.rpm or PROFILES[config.provider].free_tier.requests_per_minute
    pacer = Pacer(requests_per_minute=rpm, max_calls=args.max_calls)
    limits = RunLimits(
        max_turns=settings.run_max_turns,
        max_tool_calls=settings.run_max_tools,
        max_output_tokens_per_call=settings.run_max_output_tokens,
        max_total_tokens=settings.run_max_total_tokens,
    )
    print(
        f"agent {config.provider} {config.model_id}: {len(packs)} pack(s) x {args.repeats} "
        f"repeat(s), <= {rpm} requests/min, cap {args.max_calls} calls"
    )
    records = run_agent(
        provider,
        packs,
        repeats=args.repeats,
        provider_name=config.provider,
        model_id=config.model_id,
        limits=limits,
        max_clarification_rounds=settings.run_max_clarification_rounds,
        pacer=pacer,
        **({"explore": args.explore} if args.explore else {}),
    )
    if not records:
        print("No runs completed.", file=sys.stderr)
        return 1
    json_path, sheet_path = write_report(
        records,
        model_id=config.model_id,
        split=split,
        traces=traces,
        kind="agent",
        configuration={
            "provider": config.provider,
            "thinking_level": settings.model_thinking_level,
            "timeout_seconds": settings.model_timeout_seconds,
            "limits": {
                "max_turns": limits.max_turns,
                "max_tool_calls": limits.max_tool_calls,
                "max_output_tokens_per_call": limits.max_output_tokens_per_call,
                "max_total_tokens": limits.max_total_tokens,
                "max_clarification_rounds": settings.run_max_clarification_rounds,
            },
            "repeats": args.repeats,
            "explore": args.explore or "default",
            "packs": [pack.id for pack in packs],
        },
    )
    for mode, row in summarize(records).items():
        print(f"\n{mode}:")
        for name, value in row.items():
            print(f"  {name:36} {value if not isinstance(value, float) else round(value, 3)}")
    for record in records:
        failed = [r["annotation_id"] for r in record.results if r["verdict"] == "fail"]
        m = record.metrics
        asked = f"{m.get('agent_decisions_asked')}/{m.get('agent_decisions_needed')}"
        print(
            f"  {record.pack} #{record.repeat}: {'ok' if record.valid else record.error}; "
            f"asked {asked} decisions, {m.get('agent_questions_unneeded')} unneeded, "
            f"{m.get('agent_questions_reasked')} re-asked"
            + (f"; failed {', '.join(failed)}" if failed else "")
        )
    print(f"\nReport: {json_path}\nReview sheet: {sheet_path}")
    return 0


def _reply(args: argparse.Namespace) -> int:
    from scopesteps.agent.client import PROFILES, RunLimits, create_model_provider, paced
    from scopesteps.api.settings import get_settings
    from scopesteps.evals.reply_runner import (
        run_replies,
        select_questions,
        summarize_replies,
        write_reply_report,
    )
    from scopesteps.evals.runner import Pacer

    # Held-out packs carry no reply questions, so only the dev split is scored.
    settings = get_settings()
    config = (
        settings.provider_config(args.provider, args.model)
        if args.provider
        else settings.active_model(args.model)
    )
    if config is None:
        print("Set MODEL_PROVIDER and that provider's API key in .env", file=sys.stderr)
        return 2
    packs = load_packs("dev")
    if args.packs:
        wanted = set(args.packs.split(","))
        packs = [pack for pack in packs if pack.id in wanted]
    if args.questions:
        packs = select_questions(packs, set(args.questions.split(",")))
    traces: list[dict[str, Any]] = []
    provider = paced(create_model_provider(config, trace_sink=traces.append), config)
    rpm = args.rpm or PROFILES[config.provider].free_tier.requests_per_minute
    pacer = Pacer(requests_per_minute=rpm, max_calls=args.max_calls)
    limits = RunLimits(
        max_turns=settings.run_max_turns,
        max_tool_calls=settings.run_max_tools,
        max_output_tokens_per_call=settings.run_max_output_tokens,
        max_total_tokens=settings.run_max_total_tokens,
    )
    questions = sum(len(pack.replies.questions) for pack in packs if pack.replies is not None)
    print(
        f"reply {args.prompt} {config.provider} {config.model_id}: {questions} question(s) x "
        f"{args.repeats} "
        f"repeat(s), <= {rpm} requests/min, cap {args.max_calls} calls"
    )
    records = run_replies(
        provider,
        packs,
        repeats=args.repeats,
        provider_name=config.provider,
        model_id=config.model_id,
        limits=limits,
        pacer=pacer,
        prompt=args.prompt,
    )
    if not records:
        print("No replies completed.", file=sys.stderr)
        return 1
    json_path, sheet_path = write_reply_report(
        records,
        model_id=config.model_id,
        split="dev",
        prompt=args.prompt,
        traces=traces,
        configuration={
            "provider": config.provider,
            "thinking_level": settings.model_thinking_level,
            "timeout_seconds": settings.model_timeout_seconds,
            "max_output_tokens": settings.run_max_output_tokens,
            "repeats": args.repeats,
            "packs": [pack.id for pack in packs],
        },
    )
    for name, value in summarize_replies(records).items():
        print(f"  {name:36} {value}")
    for record in records:
        print(
            f"  {record.pack} {record.question_id} #{record.repeat}: {record.verdict} "
            f"({record.reason})"
        )
    print(f"\nReport: {json_path}\nReview sheet: {sheet_path}")
    return 0


def _change(args: argparse.Namespace) -> int:
    from scopesteps.agent.client import PROFILES, RunLimits, create_model_provider, paced
    from scopesteps.api.settings import get_settings
    from scopesteps.evals.change_runner import run_changes, summarize_changes, write_change_report
    from scopesteps.evals.runner import Pacer

    # Dev packs only: the held-out change requests stay blind until the final comparison.
    settings = get_settings()
    config = (
        settings.provider_config(args.provider, args.model)
        if args.provider
        else settings.active_model(args.model)
    )
    if config is None:
        print("Set MODEL_PROVIDER and that provider's API key in .env", file=sys.stderr)
        return 2
    packs = load_packs("dev")
    if args.packs:
        wanted = set(args.packs.split(","))
        packs = [pack for pack in packs if pack.id in wanted]
    traces: list[dict[str, Any]] = []
    provider = paced(create_model_provider(config, trace_sink=traces.append), config)
    rpm = args.rpm or PROFILES[config.provider].free_tier.requests_per_minute
    pacer = Pacer(requests_per_minute=rpm, max_calls=args.max_calls)
    limits = RunLimits(
        max_turns=settings.run_max_turns,
        max_tool_calls=settings.run_max_tools,
        max_output_tokens_per_call=settings.run_max_output_tokens,
        max_total_tokens=settings.run_max_total_tokens,
    )
    print(
        f"change {config.provider} {config.model_id}: {len(packs)} pack(s) x {args.repeats} "
        f"repeat(s), <= {rpm} requests/min, cap {args.max_calls} calls"
    )
    records = run_changes(
        provider,
        packs,
        repeats=args.repeats,
        provider_name=config.provider,
        model_id=config.model_id,
        limits=limits,
        max_clarification_rounds=settings.run_max_clarification_rounds,
        pacer=pacer,
    )
    if not records:
        print("No change runs completed.", file=sys.stderr)
        return 1
    json_path, sheet_path = write_change_report(
        records,
        model_id=config.model_id,
        split="dev",
        traces=traces,
        configuration={
            "provider": config.provider,
            "thinking_level": settings.model_thinking_level,
            "timeout_seconds": settings.model_timeout_seconds,
            "max_output_tokens": settings.run_max_output_tokens,
            "repeats": args.repeats,
            "packs": [pack.id for pack in packs],
        },
    )
    for name, value in summarize_changes(records).items():
        print(f"  {name:36} {value}")
    for record in records:
        failed = [r["annotation_id"] for r in record.results if r["verdict"] == "fail"]
        print(
            f"  {record.pack} #{record.repeat}: {record.outcome or record.error}"
            + (f"; failed {', '.join(failed)}" if failed else "")
        )
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
    single.add_argument("--repeats", type=int, default=5)
    single.add_argument(
        "--provider", choices=["gemini", "groq"], help="Provider (default: MODEL_PROVIDER)"
    )
    single.add_argument("--model", help="Model ID (default: the provider's model)")
    single.add_argument(
        "--rpm", type=int, help="Requests per minute to stay under (default: per provider)"
    )
    single.add_argument("--max-calls", type=int, default=60, help="Model calls allowed in this run")
    single.add_argument(
        "--prompt",
        choices=["draft-v1", "draft-v2", "draft-v3", "draft-v4", "draft-v6"],
        default="draft-v3",
    )
    single.add_argument(
        "--no-checks", action="store_true", help="Skip draft checks (reproduces the v1 baseline)"
    )
    agent = commands.add_parser("agent", help="Run and score full agent runs (explore, ask, draft)")
    agent.add_argument("--split", choices=["dev", "heldout"], default="dev")
    agent.add_argument("--final", action="store_true", help="Required to run held-out packs")
    agent.add_argument("--packs", help="Comma-separated pack IDs (default: all in the split)")
    agent.add_argument("--repeats", type=int, default=5)
    agent.add_argument(
        "--provider", choices=["gemini", "groq"], help="Provider (default: MODEL_PROVIDER)"
    )
    agent.add_argument("--model", help="Model ID (default: the provider's model)")
    agent.add_argument("--rpm", type=int, help="Requests per minute to stay under")
    agent.add_argument("--max-calls", type=int, default=80, help="Model calls allowed in this run")
    agent.add_argument(
        "--explore",
        choices=["explore-v1", "explore-v2"],
        help="Explore prompt (default: the one agent runs use)",
    )
    reply = commands.add_parser("reply", help="Run and score replies to the dev reply questions")
    reply.add_argument("--packs", help="Comma-separated pack IDs (default: all dev packs)")
    reply.add_argument("--repeats", type=int, default=2)
    reply.add_argument(
        "--provider", choices=["gemini", "groq"], help="Provider (default: MODEL_PROVIDER)"
    )
    reply.add_argument("--model", help="Model ID (default: the provider's model)")
    reply.add_argument("--rpm", type=int, help="Requests per minute to stay under")
    reply.add_argument("--max-calls", type=int, default=40, help="Model calls allowed in this run")
    reply.add_argument(
        "--prompt",
        choices=["reply-v1", "reply-v2"],
        default="reply-v1",
        help="Reply prompt (default: reply-v1, the one reply runs use)",
    )
    reply.add_argument("--questions", help="Comma-separated question IDs (default: all)")
    change = commands.add_parser("change", help="Run and score change analysis on the dev packs")
    change.add_argument("--packs", help="Comma-separated pack IDs (default: all dev packs)")
    change.add_argument("--repeats", type=int, default=3)
    change.add_argument(
        "--provider", choices=["gemini", "groq"], help="Provider (default: MODEL_PROVIDER)"
    )
    change.add_argument("--model", help="Model ID (default: the provider's model)")
    change.add_argument("--rpm", type=int, help="Requests per minute to stay under")
    change.add_argument("--max-calls", type=int, default=40, help="Model calls allowed in this run")
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
        case "agent":
            sys.exit(_agent(args))
        case "reply":
            sys.exit(_reply(args))
        case "change":
            sys.exit(_change(args))
        case _:
            sys.exit(_single_pass(args))

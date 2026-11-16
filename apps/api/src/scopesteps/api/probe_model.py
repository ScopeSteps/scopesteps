"""Live model probe: proves typed output and tool calling on each Claude model a profile uses.

Synthetic data only (the campus-room-booking dev pack). Opt-in and never run in CI because it is
billed. Each model is probed once, through the first step bound to it, with that step's effort,
output limit and timeout (ADR 0032). Writes one JSON report per model under evals/probes/.

    just probe-model [--profile PROFILE_ID] [--steps outline,reply]   # default: claude-mix-v1
"""

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scopesteps.agent.application.drafting import DRAFT_PROMPT as SYSTEM_PROMPT
from scopesteps.agent.application.drafting import DRAFT_PROMPT_VERSION as PROMPT_VERSION
from scopesteps.agent.application.drafting import sources_message as format_sources
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    DraftBacklog,
    LookupSourceArgs,
    SourceBlockInput,
    provider_schema,
)
from scopesteps.agent.client import (
    ANTHROPIC_PROVIDER,
    InvalidProfileError,
    ModelProfile,
    ModelProvider,
    Step,
    StepModel,
    catalog_request_limit,
    create_anthropic_adapter,
    create_model_router,
    load_profile,
)
from scopesteps.agent.domain.budget import (
    BudgetExceededError,
    RunCounters,
    RunLimits,
    check_can_call,
    estimate_tokens,
)
from scopesteps.agent.domain.model import (
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ToolResult,
    ToolResults,
    ToolSpec,
    UserMessage,
)
from scopesteps.api.settings import Settings, get_settings
from scopesteps.sources.client import quote_matches, split_into_blocks

REPO_ROOT = Path(__file__).resolve().parents[5]
PACK_DIR = REPO_ROOT / "evals" / "datasets" / "dev" / "campus-room-booking"
REPORT_DIR = REPO_ROOT / "evals" / "probes"
MAX_QUOTA_WAIT_SECONDS = 90.0


LOOKUP_SOURCE = ToolSpec(
    name="lookup_source",
    description=(
        "Search the project's source blocks. Read-only. Returns matching blocks with their IDs "
        "and text. Use block_ids to fetch exact blocks, or query to search by words."
    ),
    parameters=provider_schema(LookupSourceArgs),
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    latency_ms: int | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    data: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class Block:
    id: str
    file: str
    paragraph: int
    text: str


def load_blocks() -> list[Block]:
    blocks: list[Block] = []
    for file in ("brief.md", "transcript.md"):
        for block in split_into_blocks((PACK_DIR / file).read_text(encoding="utf-8")):
            blocks.append(Block(f"B{len(blocks) + 1}", file, block.ordinal, block.text))
    return blocks


def sources_message(blocks: list[Block], instruction: str) -> str:
    inputs = [SourceBlockInput(b.id, f"{b.file} paragraph {b.paragraph}", b.text) for b in blocks]
    return format_sources(inputs, instruction)


def lookup(blocks: list[Block], args: LookupSourceArgs) -> dict[str, Any]:
    if args.block_ids:
        found = [block for block in blocks if block.id in set(args.block_ids)]
    else:
        words = {word.lower().strip(".,?") for word in args.query.split() if len(word) > 3}
        found = [block for block in blocks if words & set(block.text.lower().split())]
    return {"blocks": [{"id": b.id, "text": b.text} for b in found[: args.limit]]}


def citation_problems(draft: DraftBacklog, blocks: list[Block]) -> list[str]:
    by_id = {block.id: block for block in blocks}
    citations = [c for s in draft.statements for c in s.citations]
    citations += [c for i in draft.items for cr in i.criteria for c in cr.citations]
    citations += [c for q in draft.questions for c in q.citations]
    problems: list[str] = []
    for citation in citations:
        block = by_id.get(citation.block_id)
        if block is None:
            problems.append(f"unknown block {citation.block_id}")
        elif not quote_matches(citation.quote, block.text):
            problems.append(f"quote not verbatim in {citation.block_id}")
    return problems


def scenario_signals(draft: DraftBacklog) -> dict[str, bool]:
    """Indicative only; semantic correctness is judged by humans in the evaluation."""
    item_text = " ".join(f"{i.title} {i.description}" for i in draft.items).lower()
    question_text = " ".join(f"{q.subject} {q.question}" for q in draft.questions).lower()
    return {
        "recurring_not_in_items": "recurring" not in item_text and "weekly" not in item_text,
        "cancellation_question_asked": "cancel" in question_text,
        "length_conflict_asked": "hour" in question_text,
        "recurring_classified_exclusion": any(
            s.kind == "exclusion" and "recurring" in s.summary.lower() for s in draft.statements
        ),
    }


class Probe:
    def __init__(
        self, provider: ModelProvider, settings: Settings, blocks: list[Block], max_output: int
    ) -> None:
        self.provider = provider
        self.blocks = blocks
        self.limits = RunLimits(
            max_turns=settings.run_max_turns,
            max_tool_calls=settings.run_max_tools,
            max_output_tokens_per_call=max_output,
            max_total_tokens=settings.run_max_total_tokens,
        )
        self.counters = RunCounters()

    def call(self, request: ModelRequest) -> ModelResult:
        text = request.system_instruction + "".join(
            turn.text for turn in request.history if isinstance(turn, UserMessage)
        )
        for attempt in (1, 2):
            check_can_call(self.counters, self.limits, estimate_tokens(text))
            try:
                result = self.provider.generate(request)
            except ModelProviderError as error:
                self.counters = self.counters.after_failed_call()
                # A rate limit says when to try again: wait visibly once, if it is soon.
                wait = error.retry_after_seconds or 60.0
                if error.kind == "quota" and attempt == 1 and wait <= MAX_QUOTA_WAIT_SECONDS:
                    print(f"  rate limited; waiting {wait:.0f}s, then one more try")
                    time.sleep(wait)
                    continue
                raise
            self.counters = self.counters.after_call(result)
            return result
        raise AssertionError("unreachable")

    def request(self, history: tuple[Any, ...], **overrides: Any) -> ModelRequest:
        return ModelRequest(
            system_instruction=SYSTEM_PROMPT,
            history=history,
            max_output_tokens=overrides.pop(
                "max_output_tokens", self.limits.max_output_tokens_per_call
            ),
            **overrides,
        )

    def typed_output(self) -> Check:
        message = UserMessage(sources_message(self.blocks, "Draft the backlog as JSON."))
        result = self.call(self.request((message,), output_schema=provider_schema(DraftBacklog)))
        return self._validate_draft("typed_output", result)

    def forced_tool_call(self) -> tuple[Check, ModelResult | None]:
        message = UserMessage(
            sources_message(
                self.blocks,
                "Before drafting, use lookup_source to find what the sources say about "
                "cancelling a booking.",
            )
        )
        result = self.call(
            self.request(
                (message,),
                tools=(LOOKUP_SOURCE,),
                tool_choice="any",
                allowed_tools=("lookup_source",),
            )
        )
        check = _base_check("forced_tool_call", result)
        if not result.tool_calls:
            check.passed, check.detail = False, f"no tool call (finish {result.finish_reason})"
            return check, None
        call = result.tool_calls[0]
        try:
            args = LookupSourceArgs.model_validate(dict(call.arguments))
        except ValidationError as error:
            check.passed, check.detail = False, f"invalid arguments: {error.error_count()} errors"
            check.data = {"name": call.name, "arguments": dict(call.arguments)}
            return check, None
        check.passed = call.name == "lookup_source"
        check.detail = f"{call.name} called with valid typed arguments"
        check.data = {
            "name": call.name,
            "arguments": args.model_dump(),
            "raw": dict(call.arguments),
        }
        return check, result

    def tool_round_trip(self, first: ModelResult) -> Check:
        message = UserMessage(
            sources_message(
                self.blocks,
                "Before drafting, use lookup_source to find what the sources say about "
                "cancelling a booking.",
            )
        )
        results = tuple(
            ToolResult(
                call_id=call.id,
                name=call.name,
                output=lookup(self.blocks, LookupSourceArgs.model_validate(dict(call.arguments))),
            )
            for call in first.tool_calls
        )
        follow_up = UserMessage("Now draft the backlog as JSON.")
        result = self.call(
            self.request(
                (message, first.turn, ToolResults(results), follow_up),
                tools=(LOOKUP_SOURCE,),
                tool_choice="none",
                output_schema=provider_schema(DraftBacklog),
            )
        )
        return self._validate_draft("tool_round_trip_typed_output", result)

    def output_limit(self) -> Check:
        message = UserMessage(sources_message(self.blocks, "Draft the backlog as JSON."))
        result = self.call(
            self.request(
                (message,), output_schema=provider_schema(DraftBacklog), max_output_tokens=64
            )
        )
        check = _base_check("output_limit_is_detected", result)
        try:
            DraftBacklog.model_validate_json(result.text or "")
            valid = True
        except ValidationError:
            valid = False
        check.passed = result.finish_reason == "max_tokens" or not valid
        check.detail = (
            f"finish={result.finish_reason}, status={result.provider_status}, "
            f"output {'valid' if valid else 'rejected by validation'}"
        )
        return check

    def _validate_draft(self, name: str, result: ModelResult) -> Check:
        check = _base_check(name, result)
        try:
            draft = DraftBacklog.model_validate_json(result.text or "")
        except ValidationError as error:
            check.passed = False
            check.detail = f"schema validation failed: {error.errors()[0]['msg']}"
            check.data = {"text_head": (result.text or "")[:500]}
            return check
        problems = citation_problems(draft, self.blocks)
        check.passed = not problems
        check.detail = (
            f"valid {DRAFT_SCHEMA_VERSION}: {len(draft.items)} items, "
            f"{len(draft.questions)} questions, {len(draft.statements)} statements; "
            f"citation problems: {len(problems)}"
        )
        check.data = {
            "citation_problems": problems,
            "scenario_signals": scenario_signals(draft),
            "draft": draft.model_dump(),
        }
        return check


def _base_check(name: str, result: ModelResult) -> Check:
    return Check(
        name=name,
        passed=False,
        detail="",
        latency_ms=result.latency_ms,
        usage=asdict(result.usage),
        finish_reason=result.finish_reason,
    )


def _guard(name: str, run: Callable[[], Check]) -> Check:
    try:
        return run()
    except (ModelProviderError, BudgetExceededError) as error:
        kind = error.kind if isinstance(error, ModelProviderError) else error.code
        return Check(name, False, f"{kind}: {error.message}")


def _discard(_event: dict[str, Any]) -> None:
    """The probe writes its own report, so per-call trace events are not needed."""


def _api_details() -> dict[str, Any]:
    return {
        "sdk": f"anthropic {version('anthropic')}",
        "api": "messages",
        "streamed": True,
        "sdk_retries": 0,
    }


def invalid_key_check(model: StepModel) -> Check:
    bad = StepModel(model.step, model.binding, create_anthropic_adapter("invalid-key-for-probe"))
    request = ModelRequest(
        system_instruction="Reply OK.", history=(UserMessage("Hi"),), max_output_tokens=16
    )
    try:
        bad.generate(request)
    except ModelProviderError as error:
        return Check(
            "invalid_key_is_classified",
            error.kind == "auth" and not error.retryable,
            f"kind={error.kind}, retryable={error.retryable}, status={error.status_code}",
        )
    return Check("invalid_key_is_classified", False, "call unexpectedly succeeded")


def steps_to_probe(profile: ModelProfile, names: str | None) -> list[Step]:
    """The named steps, or the first step bound to each model the profile uses."""
    if names:
        return [Step(name) for name in names.split(",")]
    first: dict[str, Step] = {}
    for step in Step:
        first.setdefault(profile.bindings[step].model, step)
    return list(first.values())


def main() -> None:
    parser = argparse.ArgumentParser(prog="scopesteps-probe-model")
    parser.add_argument("--profile", default="claude-mix-v1", help="Model profile to probe")
    parser.add_argument(
        "--steps", help="Comma-separated steps (default: the first step of each model)"
    )
    args = parser.parse_args()

    settings = get_settings()
    try:
        profile = load_profile(args.profile)
    except InvalidProfileError as error:
        sys.exit(str(error))
    if profile.providers != frozenset({ANTHROPIC_PROVIDER}):
        sys.exit(f"The probe calls Claude; {profile.id} does not.")
    if settings.anthropic_api_key is None:
        sys.exit("Set ANTHROPIC_API_KEY in .env first")
    api_key = settings.anthropic_api_key.get_secret_value()
    router = create_model_router(
        {ANTHROPIC_PROVIDER: create_anthropic_adapter(api_key)},
        trace_sink=_discard,
        request_limit=catalog_request_limit,
    )
    blocks = load_blocks()
    for step in steps_to_probe(profile, args.steps):
        _probe_step(router.route(profile.bindings, step), profile, settings, blocks, api_key)


def _probe_step(
    model: StepModel, profile: ModelProfile, settings: Settings, blocks: list[Block], api_key: str
) -> None:
    binding = model.binding
    print(f"{binding.model} as {model.step.value} ({binding.effort} effort):")
    probe = Probe(model, settings, blocks, binding.max_output_tokens)
    checks = [_guard("typed_output", probe.typed_output)]
    try:
        tool_check, first = probe.forced_tool_call()
    except ModelProviderError as error:
        tool_check, first = Check("forced_tool_call", False, f"{error.kind}: {error.message}"), None
    checks.append(tool_check)
    if first is not None:
        checks.append(_guard("tool_round_trip_typed_output", lambda: probe.tool_round_trip(first)))
    checks.append(_guard("output_limit_is_detected", probe.output_limit))
    checks.append(invalid_key_check(model))

    probed_at = datetime.now(UTC).isoformat(timespec="seconds")
    report = {
        "probed_at": probed_at,
        "provider": binding.provider,
        "model_id": binding.model,
        **_api_details(),
        "configuration": {
            "profile": profile.id,
            "profile_hash": profile.content_hash,
            "step": model.step.value,
            "effort": binding.effort,
            "timeout_seconds": binding.timeout_seconds,
            "max_output_tokens": binding.max_output_tokens,
            "run_max_total_tokens": settings.run_max_total_tokens,
        },
        "prompt_version": PROMPT_VERSION,
        "schema_version": DRAFT_SCHEMA_VERSION,
        "schema_sha256": hashlib.sha256(
            json.dumps(provider_schema(DraftBacklog), sort_keys=True).encode()
        ).hexdigest(),
        "fixture": "evals/datasets/dev/campus-room-booking",
        "totals": asdict(probe.counters),
        "checks": [asdict(check) for check in checks],
    }
    serialized = json.dumps(report, indent=2)
    if api_key in serialized:
        sys.exit("Refusing to write a report that contains the API key")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{probed_at[:10]}-{binding.model.replace('/', '_')}.json"
    path.write_text(serialized + "\n", encoding="utf-8")

    for check in checks:
        print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
    print(f"  Totals: {probe.counters}. Report: {path.relative_to(REPO_ROOT)}")

"""Live model probe: proves typed output and tool calling on the configured model.

Synthetic data only (the campus-room-booking dev pack). Opt-in and never run in CI because it
uses real quota. Writes a JSON report under evals/probes/ with the exact model and configuration.

    just probe-model [--model gemini-3.5-flash-lite]
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scopesteps.agent.application.drafting import DRAFT_PROMPT as SYSTEM_PROMPT
from scopesteps.agent.application.drafting import DRAFT_PROMPT_VERSION as PROMPT_VERSION
from scopesteps.agent.application.drafting import SourceBlockInput
from scopesteps.agent.application.drafting import sources_message as format_sources
from scopesteps.agent.application.schemas import (
    DRAFT_SCHEMA_VERSION,
    DraftBacklog,
    LookupSourceArgs,
    provider_schema,
)
from scopesteps.agent.domain.budget import (
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
from scopesteps.agent.infrastructure.providers.gemini import NO_RETRIES, GeminiProvider
from scopesteps.api.settings import Settings, get_settings
from scopesteps.sources.client import quote_matches, split_into_blocks

REPO_ROOT = Path(__file__).resolve().parents[5]
PACK_DIR = REPO_ROOT / "evals" / "datasets" / "dev" / "campus-room-booking"
REPORT_DIR = REPO_ROOT / "evals" / "probes"


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
    def __init__(self, provider: GeminiProvider, settings: Settings, blocks: list[Block]) -> None:
        self.provider = provider
        self.blocks = blocks
        self.limits = RunLimits(
            max_turns=settings.run_max_turns,
            max_tool_calls=settings.run_max_tools,
            max_output_tokens_per_call=settings.run_max_output_tokens,
            max_total_tokens=settings.run_max_total_tokens,
        )
        self.counters = RunCounters()

    def call(self, request: ModelRequest) -> ModelResult:
        text = request.system_instruction + "".join(
            turn.text for turn in request.history if isinstance(turn, UserMessage)
        )
        check_can_call(self.counters, self.limits, estimate_tokens(text))
        try:
            result = self.provider.generate(request)
        except ModelProviderError:
            self.counters = self.counters.after_failed_call()
            raise
        self.counters = self.counters.after_call(result)
        return result

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
    except ModelProviderError as error:
        return Check(name, False, f"{error.kind}: {error.message}")


def invalid_key_check(settings: Settings, model_id: str) -> Check:
    provider = GeminiProvider(
        api_key="invalid-key-for-probe",
        model_id=model_id,
        timeout_seconds=settings.model_timeout_seconds,
        thinking_level=settings.model_thinking_level,
    )
    request = ModelRequest(
        system_instruction="Reply OK.", history=(UserMessage("Hi"),), max_output_tokens=8
    )
    try:
        provider.generate(request)
    except ModelProviderError as error:
        return Check(
            "invalid_key_is_classified",
            error.kind == "auth" and not error.retryable,
            f"kind={error.kind}, retryable={error.retryable}, status={error.status_code}",
        )
    return Check("invalid_key_is_classified", False, "call unexpectedly succeeded")


def main() -> None:
    parser = argparse.ArgumentParser(prog="scopesteps-probe-model")
    parser.add_argument("--model", help="Model ID to probe (defaults to MODEL_ID)")
    args = parser.parse_args()

    settings = get_settings()
    if settings.model_provider != "gemini" or settings.model_api_key is None:
        sys.exit("Set MODEL_PROVIDER=gemini, MODEL_ID and MODEL_API_KEY in .env first")
    model_id = args.model or settings.model_id or ""
    api_key = settings.model_api_key.get_secret_value()

    provider = GeminiProvider(
        api_key=api_key,
        model_id=model_id,
        timeout_seconds=settings.model_timeout_seconds,
        thinking_level=settings.model_thinking_level,
    )
    probe = Probe(provider, settings, load_blocks())
    checks = [_guard("typed_output", probe.typed_output)]
    try:
        tool_check, first = probe.forced_tool_call()
    except ModelProviderError as error:
        tool_check, first = Check("forced_tool_call", False, f"{error.kind}: {error.message}"), None
    checks.append(tool_check)
    if first is not None:
        checks.append(_guard("tool_round_trip_typed_output", lambda: probe.tool_round_trip(first)))
    checks.append(_guard("output_limit_is_detected", probe.output_limit))
    checks.append(invalid_key_check(settings, model_id))

    probed_at = datetime.now(UTC).isoformat(timespec="seconds")
    report = {
        "probed_at": probed_at,
        "provider": "gemini",
        "model_id": model_id,
        "sdk": f"google-genai {version('google-genai')}",
        "api": "interactions",
        "configuration": {
            "store": False,
            "sdk_retries": NO_RETRIES.model_dump(exclude_none=True),
            "thinking_level": settings.model_thinking_level,
            "timeout_seconds": settings.model_timeout_seconds,
            "max_output_tokens": settings.run_max_output_tokens,
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
    path = REPORT_DIR / f"{probed_at[:10]}-{model_id}.json"
    path.write_text(serialized + "\n", encoding="utf-8")

    for check in checks:
        print(f"{'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")
    print(f"Totals: {probe.counters}. Report: {path.relative_to(REPO_ROOT)}")

"""One content-free outcome record per finished agent run, sent through the same sink as model
calls: exported over OTLP when export is on, logged otherwise (ADR 0022).

A run finishes once: every finished status is final and the save that sets it is a revision
check, so the use cases that make that save emit the record, after their commit.
"""

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from scopesteps.agent.application.steps import VALIDATE_CHANGE
from scopesteps.agent.application.tools import VALIDATE_BACKLOG
from scopesteps.agent.domain.budget import MICROUSD_PER_USD
from scopesteps.agent.domain.providers import REPLAY_PROVIDER
from scopesteps.agent.domain.run import Question, Run, RunStep

RUN_OUTCOME_EVENT = "scopesteps.agent.run"
_logger = logging.getLogger("scopesteps.agent.runs")
_VALIDATIONS = frozenset({VALIDATE_BACKLOG, VALIDATE_CHANGE})

OutcomeSink = Callable[[dict[str, Any]], None]

RUN_KINDS = {"initial": "draft", "change": "change", "reply": "reply", "tasks": "tasks"}


@dataclass(frozen=True)
class RunOutcome:
    """Ids, versions, counts and codes only: never a prompt, source text, answer, model output,
    error message or problem text."""

    run_id: str
    kind: str
    status: str
    error_code: str | None
    prompt_version: str
    provider: str
    model_id: str
    served_by: str
    """primary, or backup when the run moved to the backup provider (ADR 0006)."""
    replay: bool
    model_turns: int
    total_tokens: int
    cost_usd: Decimal
    problems: int
    """Check problems left after the repair, from the run's last validation."""
    problem_codes: tuple[str, ...]
    repaired: bool
    """Whether a repair call was made, whatever it achieved."""
    questions_asked: int
    duration_ms: int
    """From the run's creation to its outcome, waiting for answers included."""


def run_outcome(run: Run, steps: Sequence[RunStep], questions: Sequence[Question]) -> RunOutcome:
    validation = next(
        (step for step in reversed(steps) if step.kind == "tool" and step.name in _VALIDATIONS),
        None,
    )
    detail = {} if validation is None else validation.detail
    codes = detail.get("problem_codes", [])
    problems = detail.get("problems", 0)
    return RunOutcome(
        run_id=str(run.id),
        kind=RUN_KINDS[run.mode],
        status=run.status.value,
        error_code=None if run.error is None else run.error.code,
        prompt_version=run.inputs.prompt_version,
        provider=run.inputs.provider,
        model_id=run.inputs.model_id,
        served_by="primary" if run.inputs.fallback_reason is None else "backup",
        replay=run.inputs.provider == REPLAY_PROVIDER,
        model_turns=run.counters.model_turns,
        total_tokens=run.counters.total_tokens,
        cost_usd=Decimal(run.totals.cost_microusd) / MICROUSD_PER_USD,
        problems=problems if isinstance(problems, int) else 0,
        problem_codes=tuple(str(code) for code in cast(list[object], codes))
        if isinstance(codes, list)
        else (),
        repaired=any(step.kind == "model_call" and step.repair != "none" for step in steps),
        questions_asked=len(questions),
        duration_ms=max(0, round((run.updated_at - run.created_at).total_seconds() * 1000)),
    )


def outcome_event(outcome: RunOutcome) -> dict[str, Any]:
    """The record as a sink event, named like the model-call events (`scopesteps.*` attributes,
    `error.type` for the error code)."""
    return {
        "name": RUN_OUTCOME_EVENT,
        "duration_ms": outcome.duration_ms,
        "error.type": outcome.error_code,
        "scopesteps.run_id": outcome.run_id,
        "scopesteps.run.kind": outcome.kind,
        "scopesteps.run.status": outcome.status,
        "scopesteps.prompt_version": outcome.prompt_version,
        "scopesteps.run.provider": outcome.provider,
        "scopesteps.run.model": outcome.model_id,
        "scopesteps.run.served_by": outcome.served_by,
        "scopesteps.replay": outcome.replay,
        "scopesteps.run.model_turns": outcome.model_turns,
        "scopesteps.run.total_tokens": outcome.total_tokens,
        "scopesteps.cost_usd_estimate": f"{outcome.cost_usd:.6f}",
        "scopesteps.run.problems": outcome.problems,
        "scopesteps.run.problem_codes": list(outcome.problem_codes),
        "scopesteps.run.repaired": outcome.repaired,
        "scopesteps.run.questions": outcome.questions_asked,
    }


def log_outcome(event: dict[str, Any]) -> None:
    """The sink when export is off: one JSON line per finished run."""
    _logger.info(json.dumps(event, sort_keys=True))


def emit(sink: OutcomeSink | None, outcome: RunOutcome | None) -> None:
    """Send a run's record, if it finished, once its transaction has committed. The outcome is
    already stored, so a failing sink is logged by its error's type and never fails the request."""
    if sink is None or outcome is None:
        return
    try:
        sink(outcome_event(outcome))
    except Exception as error:
        _logger.warning("Could not send a run outcome record (%s)", type(error).__name__)

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from scopesteps.agent.application.outcomes import (
    RunOutcome,
    emit,
    log_outcome,
    outcome_event,
    run_outcome,
)
from scopesteps.agent.client import load_profile
from scopesteps.agent.domain.budget import RunCounters, RunLimits
from scopesteps.agent.domain.ids import RunId
from scopesteps.agent.domain.run import (
    Run,
    RunError,
    RunInputs,
    RunMode,
    RunStage,
    RunStatus,
    TokenTotals,
)
from scopesteps.agent.infrastructure.telemetry import EXPORTED_ATTRIBUTES
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId

FAKE_PROFILE = load_profile("fake")
NOW = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
PRIVATE_MESSAGE = "The model quoted CONFIDENTIAL source text"
RUN = Run(
    id=RunId(uuid4()),
    project_id=ProjectId(uuid4()),
    mode="initial",
    status=RunStatus.FAILED,
    stage=RunStage.DRAFT,
    revision=4,
    inputs=RunInputs(
        source_version_ids=(uuid4(),),
        model_profile_id=FAKE_PROFILE.id,
        model_profile_hash=FAKE_PROFILE.content_hash,
        model_bindings=FAKE_PROFILE.bindings,
        prompt_version="draft-v10+abc",
        schema_version="draft-backlog.v5",
        limits=RunLimits(
            max_turns=6, max_tool_calls=8, max_output_tokens_per_call=8000, max_total_tokens=200_000
        ),
        max_clarification_rounds=2,
    ),
    created_by=UserId(UUID(int=5)),
    created_at=NOW,
    updated_at=NOW + timedelta(seconds=12, milliseconds=345),
    counters=RunCounters(model_turns=2, tool_calls=1, total_tokens=4200),
    totals=TokenTotals(cost_microusd=1234),
    problems=(PRIVATE_MESSAGE,),
    error=RunError("INVALID_MODEL_OUTPUT", PRIVATE_MESSAGE, retryable=False),
)


@pytest.mark.parametrize(
    ("mode", "kind"), [("initial", "draft"), ("change", "change"), ("reply", "reply")]
)
def test_each_run_mode_is_reported_as_its_kind(mode: RunMode, kind: str) -> None:
    assert run_outcome(replace(RUN, mode=mode), (), ()).kind == kind


def test_the_record_holds_counts_codes_and_cost_and_never_messages() -> None:
    outcome = run_outcome(RUN, (), ())
    event = outcome_event(outcome)

    assert (outcome.error_code, outcome.duration_ms, outcome.model_turns) == (
        "INVALID_MODEL_OUTPUT",
        12345,
        2,
    )
    assert event["scopesteps.cost_usd_estimate"] == "0.001234"
    assert PRIVATE_MESSAGE not in json.dumps(event)


def test_every_record_attribute_is_on_the_export_allow_list() -> None:
    event = outcome_event(run_outcome(RUN, (), ()))

    assert set(event) - {"name", "duration_ms"} <= EXPORTED_ATTRIBUTES


def test_a_replay_says_so_and_names_the_pinned_profile() -> None:
    replay = load_profile("replay")
    replayed = replace(
        RUN,
        inputs=replace(
            RUN.inputs,
            model_profile_id=replay.id,
            model_profile_hash=replay.content_hash,
            model_bindings=replay.bindings,
        ),
    )

    outcome = run_outcome(replayed, (), ())

    assert (outcome.replay, outcome.provider, outcome.model_id) == (True, "replay", "replay")
    assert run_outcome(RUN, (), ()).replay is False


def test_without_export_the_record_is_one_log_line(caplog: pytest.LogCaptureFixture) -> None:
    outcome: RunOutcome = run_outcome(RUN, (), ())

    with caplog.at_level(logging.INFO, logger="scopesteps.agent.runs"):
        emit(log_outcome, outcome)
        emit(None, outcome)
        emit(log_outcome, None)

    (record,) = caplog.records
    assert json.loads(record.getMessage())["scopesteps.run.status"] == "failed"


def test_a_failing_sink_never_fails_the_request(caplog: pytest.LogCaptureFixture) -> None:
    def broken(event: dict[str, object]) -> None:
        raise RuntimeError(PRIVATE_MESSAGE)

    with caplog.at_level(logging.WARNING, logger="scopesteps.agent.runs"):
        emit(broken, run_outcome(RUN, (), ()))

    assert "RuntimeError" in caplog.text
    assert PRIVATE_MESSAGE not in caplog.text

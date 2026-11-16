from dataclasses import replace
from typing import Any

import pytest

from scopesteps.agent.domain.budget import RunLimits
from scopesteps.agent.domain.model import ModelRequest, ModelResult, ModelTurn, Usage
from scopesteps.agent.domain.profiles import (
    InvalidProfileError,
    ModelNotServedError,
    Step,
    StepBinding,
)
from scopesteps.agent.infrastructure.profiles import load_profile, profile_ids
from scopesteps.agent.infrastructure.providers.fake import ScriptedProvider
from scopesteps.agent.infrastructure.routing import ModelRouter, catalog_request_limit

CLAUDE_MIX_V1 = {
    "explore": ("claude-sonnet-5-5", "medium", 12000, 180),
    "outline": ("claude-sonnet-5-5", "high", 32000, 420),
    "epic_stories": ("claude-haiku-5-5", "medium", 12000, 120),
    "change_explore": ("claude-sonnet-5-5", "medium", 12000, 180),
    "change": ("claude-sonnet-5-5", "high", 16000, 240),
    "reply": ("claude-haiku-5-5", "low", 4000, 60),
    "suggest_tasks": ("claude-haiku-5-5", "low", 8000, 120),
}


def _result() -> ModelResult:
    return ModelResult(
        provider="fake",
        model_id="answered-by",
        turn=ModelTurn(()),
        text="ok",
        tool_calls=(),
        finish_reason="completed",
        usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
        latency_ms=1,
    )


def test_every_shipped_profile_loads_and_hashes_the_same_each_time() -> None:
    ids = profile_ids()

    assert set(ids) >= {"claude-mix-v1", "fake", "replay"}
    for profile_id in ids:
        profile = load_profile(profile_id)
        assert profile.id == profile_id
        assert profile.content_hash == load_profile.__wrapped__(profile_id).content_hash


def test_claude_mix_v1_binds_each_step_as_decided() -> None:
    profile = load_profile("claude-mix-v1")

    bound = {
        step.value: (b.model, b.effort, b.max_output_tokens, b.timeout_seconds)
        for step, b in profile.bindings.items()
    }

    assert bound == CLAUDE_MIX_V1
    assert profile.providers == {"anthropic"}
    assert profile.longest_timeout_seconds == 420


@pytest.mark.parametrize("profile_id", ["fake", "replay"])
def test_the_offline_profiles_use_the_claude_mix_models_without_calling_them(
    profile_id: str,
) -> None:
    profile = load_profile(profile_id)

    models = {step.value: binding.model for step, binding in profile.bindings.items()}

    assert models == {step: values[0] for step, values in CLAUDE_MIX_V1.items()}
    assert profile.providers == {profile_id}


def test_an_unknown_profile_is_refused() -> None:
    with pytest.raises(InvalidProfileError, match="Unknown model profile"):
        load_profile("gemini-flash-lite")


def test_the_router_sends_each_request_with_its_step_binding() -> None:
    profile = load_profile("claude-mix-v1")
    adapter = ScriptedProvider([_result(), _result()])
    router = ModelRouter({"anthropic": adapter}, trace_sink=lambda event: None)

    outline = router.route(profile.bindings, Step.OUTLINE)
    reply = router.route(profile.bindings, Step.REPLY)
    outline.generate(ModelRequest(system_instruction="s", history=(), max_output_tokens=10))
    reply.generate(ModelRequest(system_instruction="s", history=(), max_output_tokens=10))

    sent = [(r.model, r.effort, r.timeout_seconds) for r in adapter.requests]
    assert sent == [("claude-sonnet-5-5", "high", 420), ("claude-haiku-5-5", "low", 60)]
    assert (
        outline.limits(
            RunLimits(
                max_turns=1, max_tool_calls=1, max_output_tokens_per_call=1, max_total_tokens=1
            )
        ).max_output_tokens_per_call
        == 32000
    )


def test_a_provider_the_router_does_not_serve_is_refused_not_replaced() -> None:
    profile = load_profile("claude-mix-v1")
    router = ModelRouter({"fake": ScriptedProvider([])}, trace_sink=lambda event: None)

    assert not router.serves(profile.bindings)
    with pytest.raises(ModelNotServedError, match="anthropic claude-sonnet-5-5"):
        router.route(profile.bindings, Step.EXPLORE)


def test_the_request_limit_comes_from_the_binding() -> None:
    profile = load_profile("claude-mix-v1")

    def limit(binding: StepBinding) -> int | None:
        return 200_000 if binding.model == "claude-haiku-5-5" else None

    router = ModelRouter(
        {"anthropic": ScriptedProvider([])}, trace_sink=lambda event: None, request_limit=limit
    )

    assert router.route(profile.bindings, Step.REPLY).max_request_tokens == 200_000
    assert router.route(profile.bindings, Step.OUTLINE).max_request_tokens is None


def test_each_call_is_traced_with_the_model_its_request_names() -> None:
    events: list[dict[str, Any]] = []
    profile = load_profile("claude-mix-v1")
    router = ModelRouter({"anthropic": ScriptedProvider([_result()])}, trace_sink=events.append)

    router.route(profile.bindings, Step.EPIC_STORIES).generate(
        ModelRequest(system_instruction="s", history=(), max_output_tokens=10)
    )

    (event,) = events
    assert (event["gen_ai.provider.name"], event["gen_ai.request.model"]) == (
        "anthropic",
        "claude-haiku-5-5",
    )


def test_each_call_is_traced_with_its_step_and_the_runs_profile() -> None:
    events: list[dict[str, Any]] = []
    router = ModelRouter({"anthropic": ScriptedProvider([_result()])}, trace_sink=events.append)
    profile = load_profile("claude-mix-v1")
    model = replace(
        router.route(profile.bindings, Step.OUTLINE),
        profile_id=profile.id,
        profile_hash=profile.content_hash,
    )

    model.generate(ModelRequest("policy", (), max_output_tokens=10))

    (event,) = events
    assert event["scopesteps.step"] == "outline"
    assert event["scopesteps.model_profile_id"] == "claude-mix-v1"
    assert event["scopesteps.model_profile_hash"] == profile.content_hash


def test_the_catalog_gives_each_claude_binding_its_models_input_limit() -> None:
    profile = load_profile("claude-mix-v1")
    router = ModelRouter({"anthropic": ScriptedProvider([])}, request_limit=catalog_request_limit)

    limits = {step: router.route(profile.bindings, step).max_request_tokens for step in Step}

    assert set(limits.values()) == {1_000_000}
    assert catalog_request_limit(load_profile("fake").bindings[Step.REPLY]) is None

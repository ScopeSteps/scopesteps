import pytest

from scopesteps.agent.domain.model import ModelProviderError, ModelRequest, Usage
from scopesteps.agent.domain.profiles import (
    InvalidProfileError,
    ModelProfile,
    Step,
    StepBinding,
)


def _binding(model: str = "model-a", **overrides: object) -> dict[str, object]:
    return {
        "provider": "fake",
        "model": model,
        "effort": "medium",
        "max_output_tokens": 1000,
        "timeout_seconds": 60,
        **overrides,
    }


def _steps(**overrides: dict[str, object]) -> dict[str, object]:
    return {step.value: overrides.get(step.value, _binding()) for step in Step}


def test_profile_hash_ignores_the_order_steps_are_written_in() -> None:
    steps = _steps(reply=_binding("model-b"))

    forwards = ModelProfile.from_mapping("mix", steps)
    backwards = ModelProfile.from_mapping("mix", dict(reversed(list(steps.items()))))

    assert forwards.content_hash == backwards.content_hash
    assert len(forwards.content_hash) == 64


@pytest.mark.parametrize(
    ("profile_id", "steps"),
    [
        ("other-id", _steps()),
        ("mix", _steps(outline=_binding(effort="high"))),
        ("mix", _steps(change=_binding(timeout_seconds=61))),
    ],
)
def test_profile_hash_changes_with_any_content(profile_id: str, steps: dict[str, object]) -> None:
    base = ModelProfile.from_mapping("mix", _steps())

    changed = ModelProfile.from_mapping(profile_id, steps)

    assert changed.content_hash != base.content_hash


def test_profile_without_a_binding_for_every_step_is_refused() -> None:
    steps = _steps()
    del steps["suggest_tasks"]

    with pytest.raises(InvalidProfileError, match="suggest_tasks"):
        ModelProfile.from_mapping("mix", steps)


def test_profile_naming_an_unknown_step_is_refused() -> None:
    with pytest.raises(InvalidProfileError, match="draft"):
        ModelProfile.from_mapping("mix", {**_steps(), "draft": _binding()})


@pytest.mark.parametrize(
    "binding",
    [
        _binding(effort="extreme"),
        _binding(max_output_tokens=0),
        _binding(timeout_seconds=-1),
        _binding(timeout_seconds="60"),
        _binding(max_output_tokens=True),
        _binding(provider=""),
        {"provider": "fake", "model": "model-a"},
    ],
)
def test_malformed_binding_is_refused(binding: dict[str, object]) -> None:
    with pytest.raises(InvalidProfileError):
        StepBinding.from_mapping(binding)


def test_profile_round_trips_through_its_pinned_bindings() -> None:
    profile = ModelProfile.from_mapping("mix", _steps(outline=_binding("model-b")))

    pinned = ModelProfile.from_mapping(profile.id, profile.bindings_mapping())

    assert pinned == profile
    assert pinned.binding(Step.OUTLINE).model == "model-b"
    assert pinned.providers == frozenset({"fake"})


def test_longest_timeout_is_the_largest_step_timeout() -> None:
    profile = ModelProfile.from_mapping("mix", _steps(outline=_binding(timeout_seconds=420)))

    assert profile.longest_timeout_seconds == 420


def test_spend_limit_is_never_retried() -> None:
    error = ModelProviderError("spend_limit", "Spend limit reached.", status_code=429)

    assert not error.retryable


def test_new_request_and_usage_fields_default_so_old_recordings_still_load() -> None:
    usage = Usage(
        **{"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 0, "total_tokens": 15}
    )
    request = ModelRequest(system_instruction="s", history=(), max_output_tokens=10)

    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (0, 0)
    assert (request.effort, request.timeout_seconds) == (None, None)

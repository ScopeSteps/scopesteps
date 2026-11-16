"""Model profiles: which model, effort and limits each agent step uses (ADR 0032).

A profile is checked in, named and hashed. A run pins the profile's id, hash and a copy of its
bindings when it is created, so a later edit to the profile file cannot change a run in flight.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, cast, get_args

from scopesteps.kernel import DomainError
from scopesteps.kernel.errors import ConflictError

Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORTS: tuple[Effort, ...] = get_args(Effort)


class Step(StrEnum):
    """Every kind of model call the agent makes. A repair uses the model of the step it repairs."""

    EXPLORE = "explore"
    OUTLINE = "outline"
    EPIC_STORIES = "epic_stories"
    CHANGE_EXPLORE = "change_explore"
    CHANGE = "change"
    REPLY = "reply"
    SUGGEST_TASKS = "suggest_tasks"


class InvalidProfileError(DomainError):
    """A model profile that cannot be used: a step without a binding, or a limit out of range."""

    code = "MODEL_PROFILE_INVALID"


class ModelNotServedError(ConflictError):
    """A run's pinned binding names a provider this process does not serve. The run keeps its
    pinned models, so it waits until that provider is configured again, or a new run starts."""

    code = "RUN_MODEL_CHANGED"


@dataclass(frozen=True)
class StepBinding:
    provider: str
    model: str
    effort: Effort
    max_output_tokens: int
    timeout_seconds: int

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise InvalidProfileError("A step binding needs a provider and a model.")
        if self.effort not in EFFORTS:
            raise InvalidProfileError(f"Unknown effort {self.effort!r}.")
        if self.max_output_tokens <= 0 or self.timeout_seconds <= 0:
            raise InvalidProfileError("Output tokens and timeout must be positive.")

    def to_mapping(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "effort": self.effort,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> StepBinding:
        """Raises InvalidProfileError on a missing field or a value of the wrong type."""
        try:
            provider, model, effort = data["provider"], data["model"], data["effort"]
            max_output_tokens, timeout_seconds = data["max_output_tokens"], data["timeout_seconds"]
        except KeyError as missing:
            raise InvalidProfileError(f"A step binding is missing {missing}.") from None
        texts = (provider, model, effort)
        numbers = (max_output_tokens, timeout_seconds)
        if not all(isinstance(value, str) for value in texts) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in numbers
        ):
            raise InvalidProfileError("A step binding has a value of the wrong type.")
        return cls(
            provider=cast(str, provider),
            model=cast(str, model),
            effort=cast(Effort, effort),
            max_output_tokens=cast(int, max_output_tokens),
            timeout_seconds=cast(int, timeout_seconds),
        )


@dataclass(frozen=True)
class ModelProfile:
    id: str
    bindings: Mapping[Step, StepBinding]
    content_hash: str = field(init=False)
    """sha256 of the normalized content, so two files that differ only in layout hash the same."""

    def __post_init__(self) -> None:
        if not self.id:
            raise InvalidProfileError("A model profile needs an id.")
        missing = [step.value for step in Step if step not in self.bindings]
        if missing:
            raise InvalidProfileError(
                f"Model profile {self.id!r} has no binding for: {', '.join(missing)}."
            )
        object.__setattr__(self, "bindings", {step: self.bindings[step] for step in Step})
        object.__setattr__(self, "content_hash", self._hash())

    def binding(self, step: Step) -> StepBinding:
        return self.bindings[step]

    @property
    def providers(self) -> frozenset[str]:
        return frozenset(binding.provider for binding in self.bindings.values())

    @property
    def longest_timeout_seconds(self) -> int:
        return max(binding.timeout_seconds for binding in self.bindings.values())

    def bindings_mapping(self) -> dict[str, dict[str, object]]:
        """The bindings as plain data, keyed by step, as a run stores its pinned copy."""
        return {step.value: binding.to_mapping() for step, binding in self.bindings.items()}

    @classmethod
    def from_mapping(cls, profile_id: str, steps: Mapping[str, object]) -> ModelProfile:
        """Raises InvalidProfileError on an unknown step or a malformed binding."""
        known = {step.value for step in Step}
        unknown = sorted(set(steps) - known)
        if unknown:
            raise InvalidProfileError(
                f"Model profile {profile_id!r} names unknown steps: {', '.join(unknown)}."
            )
        bindings: dict[Step, StepBinding] = {}
        for name, data in steps.items():
            if not isinstance(data, Mapping):
                raise InvalidProfileError(f"Step {name!r} in {profile_id!r} is not a table.")
            bindings[Step(name)] = StepBinding.from_mapping(cast(Mapping[str, object], data))
        return cls(id=profile_id, bindings=bindings)

    def _hash(self) -> str:
        normalized = json.dumps(
            {"id": self.id, "steps": self.bindings_mapping()},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

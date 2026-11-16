"""Loads the checked-in model profiles (`profiles/<id>.toml`, ADR 0032)."""

import tomllib
from functools import cache
from importlib.resources import files
from typing import cast

from scopesteps.agent.domain.profiles import InvalidProfileError, ModelProfile

_PROFILES = files("scopesteps.agent") / "profiles"


def profile_ids() -> tuple[str, ...]:
    """Every profile shipped with the module, sorted."""
    names = (entry.name for entry in _PROFILES.iterdir() if entry.name.endswith(".toml"))
    return tuple(sorted(name.removesuffix(".toml") for name in names))


@cache
def load_profile(profile_id: str) -> ModelProfile:
    """Raises InvalidProfileError for an unknown id, or a file that is not a valid profile."""
    if profile_id not in profile_ids():
        known = ", ".join(profile_ids())
        raise InvalidProfileError(f"Unknown model profile {profile_id!r}. Known: {known}.")
    data = tomllib.loads((_PROFILES / f"{profile_id}.toml").read_text(encoding="utf-8"))
    if data.get("id") != profile_id:
        raise InvalidProfileError(f"Profile file {profile_id}.toml must say id = {profile_id!r}.")
    steps = data.get("steps")
    if not isinstance(steps, dict):
        raise InvalidProfileError(f"Profile {profile_id!r} has no [steps] tables.")
    return ModelProfile.from_mapping(profile_id, cast(dict[str, object], steps))

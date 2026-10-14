"""How a version was decided. Approvals and rejections are recorded by `change_control`, which
builds on this module, so this module reads them through a port the composition root binds."""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.identity.client import UserId


@dataclass(frozen=True)
class VersionDecision:
    version_id: BacklogVersionId
    decision: Literal["approved", "rejected"]
    decided_by: UserId
    decided_at: datetime
    baseline_number: int | None
    """1 for the project's first approved baseline, 2 for the next; None for a rejection."""


DecisionReader = Callable[
    [Collection[BacklogVersionId]], Mapping[BacklogVersionId, VersionDecision]
]
"""The decision recorded on each of the given versions; undecided versions are absent. Performs
no access check: callers pass only versions the actor may see."""

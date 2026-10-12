"""Shared kernel: primitives every ScopeSteps module may depend on."""

from scopesteps.kernel.errors import DomainError
from scopesteps.kernel.events import DomainEvent
from scopesteps.kernel.ids import new_id

__all__ = ["DomainError", "DomainEvent", "new_id"]

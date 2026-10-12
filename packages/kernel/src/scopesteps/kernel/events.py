"""Base type for domain events that modules publish to each other."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from scopesteps.kernel.ids import new_id


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: uuid.UUID = field(default_factory=new_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

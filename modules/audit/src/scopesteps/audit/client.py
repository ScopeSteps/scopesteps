"""Public interface of the audit module. Other modules depend on this file only."""

from typing import Protocol


class AuditClient(Protocol):
    """Operations other modules may call on the audit module."""

"""Public interface of the evidence module. Other modules depend on this file only."""

from typing import Protocol


class EvidenceClient(Protocol):
    """Operations other modules may call on the evidence module."""

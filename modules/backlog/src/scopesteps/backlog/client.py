"""Public interface of the backlog module. Other modules depend on this file only."""

from typing import Protocol


class BacklogClient(Protocol):
    """Operations other modules may call on the backlog module."""

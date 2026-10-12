"""Public interface of the agent module. Other modules depend on this file only."""

from typing import Protocol


class AgentClient(Protocol):
    """Operations other modules may call on the agent module."""

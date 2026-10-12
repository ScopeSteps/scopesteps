"""Public interface of the change_control module. Other modules depend on this file only."""

from typing import Protocol


class ChangeControlClient(Protocol):
    """Operations other modules may call on the change_control module."""

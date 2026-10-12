"""Public interface of the identity module. Other modules depend on this file only."""

from typing import Protocol


class IdentityClient(Protocol):
    """Operations other modules may call on the identity module."""

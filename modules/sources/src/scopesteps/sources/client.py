"""Public interface of the sources module. Other modules depend on this file only."""

from typing import Protocol


class SourcesClient(Protocol):
    """Operations other modules may call on the sources module."""

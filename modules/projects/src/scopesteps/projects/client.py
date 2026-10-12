"""Public interface of the projects module. Other modules depend on this file only."""

from typing import Protocol


class ProjectsClient(Protocol):
    """Operations other modules may call on the projects module."""

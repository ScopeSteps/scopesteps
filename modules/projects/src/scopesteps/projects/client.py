from collections.abc import Callable
from dataclasses import dataclass

from scopesteps.projects.domain.ids import ProjectId


@dataclass(frozen=True)
class ProjectRef:
    id: ProjectId
    name: str


ProjectReader = Callable[[ProjectId], ProjectRef | None]
"""A project's current name, for labelling versions and exports; None if there is no such
project. Performs no access check: callers check the actor's access to the project first."""


def get_project_reader() -> ProjectReader:
    """FastAPI dependency for modules that show a project's name.

    Projects owns the implementation; the composition root binds it with
    `app.dependency_overrides`, which keeps this module free of SQLAlchemy for the domain code
    that imports `ProjectId` from it.
    """
    raise RuntimeError("get_project_reader is not bound to the projects module's reader")


__all__ = ["ProjectId", "ProjectReader", "ProjectRef", "get_project_reader"]

from dataclasses import dataclass
from datetime import datetime

from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class Project:
    id: ProjectId
    name: str
    created_at: datetime

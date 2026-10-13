import unicodedata
from dataclasses import dataclass
from datetime import datetime

from scopesteps.kernel.errors import ConflictError, InvalidInputError
from scopesteps.projects.domain.ids import ProjectId

MAX_NAME_CHARS = 80


class InvalidProjectNameError(InvalidInputError):
    code = "PROJECT_NAME_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message, details={"field": "name", "max_chars": MAX_NAME_CHARS})


class ProjectChangedError(ConflictError):
    """The project changed after the caller read it; nothing from this request was saved."""

    code = "PROJECT_CHANGED"


class ConcurrentCommandError(ConflictError):
    code = "PROJECT_COMMAND_IN_PROGRESS"
    retryable = True


@dataclass(frozen=True)
class Project:
    id: ProjectId
    name: str
    created_at: datetime
    revision: int = 1
    """Goes up by one with every saved change, so a writer can tell its copy is stale."""


def normalize_name(raw: str) -> str:
    """The name as it is stored and compared: NFC, trimmed, with each run of whitespace (tabs
    and line breaks included) collapsed to one space. Length is counted in code points after
    that. Names need not be unique; a project is identified by its id."""
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        raise InvalidProjectNameError("Enter a project name")
    if len(name) > MAX_NAME_CHARS:
        raise InvalidProjectNameError(
            f"A project name can be at most {MAX_NAME_CHARS} characters long"
        )
    # Control and invisible characters (zero-width spaces, direction overrides) could make two
    # names look alike or a name look blank, and the activity log accepts printable text only.
    if not name.isprintable():
        raise InvalidProjectNameError(
            "A project name cannot contain control or invisible characters"
        )
    return name

import unicodedata
from dataclasses import dataclass

from scopesteps.kernel.errors import ConflictError, InvalidInputError

# SSPOC-49. The name has to fit the account menu, avatars' labels and activity entries; the about
# text is a short introduction, not a biography.
MAX_DISPLAY_NAME_CHARS = 60
MAX_JOB_TITLE_CHARS = 80
MAX_ABOUT_CHARS = 280


class InvalidProfileError(InvalidInputError):
    code = "PROFILE_INVALID"

    def __init__(self, field: str, message: str, max_chars: int) -> None:
        super().__init__(message, details={"field": field, "max_chars": max_chars})


class ProfileChangedError(ConflictError):
    """The profile changed after the caller read it; nothing from this request was saved."""

    code = "PROFILE_CHANGED"


@dataclass(frozen=True)
class Profile:
    """What a user says about themselves. Email and roles are not part of it."""

    display_name: str
    job_title: str
    about: str


def normalize_profile(display_name: str, job_title: str, about: str) -> Profile:
    """The profile as it is stored: NFC, trimmed, lengths counted in code points after that.

    The name and job title are one line, with each run of whitespace collapsed to one space. The
    about text keeps its line breaks. Control and invisible characters are refused, as in project
    names, because names appear in the activity log.
    """
    name = _one_line(display_name, "display_name", "name", MAX_DISPLAY_NAME_CHARS)
    if not name:
        raise InvalidProfileError("display_name", "Enter your name", MAX_DISPLAY_NAME_CHARS)
    title = _one_line(job_title, "job_title", "job title", MAX_JOB_TITLE_CHARS)
    text = unicodedata.normalize("NFC", about).replace("\r\n", "\n").strip()
    if len(text) > MAX_ABOUT_CHARS:
        raise InvalidProfileError(
            "about", f"About can be at most {MAX_ABOUT_CHARS} characters long", MAX_ABOUT_CHARS
        )
    if not all(char == "\n" or char.isprintable() for char in text):
        raise InvalidProfileError(
            "about", "About cannot contain control or invisible characters", MAX_ABOUT_CHARS
        )
    return Profile(display_name=name, job_title=title, about=text)


def _one_line(raw: str, field: str, label: str, max_chars: int) -> str:
    value = " ".join(unicodedata.normalize("NFC", raw).split())
    if len(value) > max_chars:
        raise InvalidProfileError(
            field, f"A {label} can be at most {max_chars} characters long", max_chars
        )
    if not value.isprintable():
        raise InvalidProfileError(
            field, f"A {label} cannot contain control or invisible characters", max_chars
        )
    return value

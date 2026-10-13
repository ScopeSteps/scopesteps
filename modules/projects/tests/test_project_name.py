import pytest

from scopesteps.projects.domain.project import (
    MAX_NAME_CHARS,
    InvalidProjectNameError,
    normalize_name,
)


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Campus Room Booking", "Campus Room Booking"),
        ("  Makerspace Tool Library \n", "Makerspace Tool Library"),
        ("Library\t  kiosk\nrefresh", "Library kiosk refresh"),
        ("x", "x"),
        ("n" * MAX_NAME_CHARS, "n" * MAX_NAME_CHARS),
        ("  " + "n" * MAX_NAME_CHARS + "  ", "n" * MAX_NAME_CHARS),
        ("Café menu", "Café menu"),
    ],
)
def test_names_are_stored_trimmed_and_normalized(raw: str, stored: str) -> None:
    assert normalize_name(raw) == stored


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "\t\n", "​", "n" * (MAX_NAME_CHARS + 1), "Room\x00booking"],
    ids=["empty", "spaces", "tabs", "zero-width", "too-long", "control-character"],
)
def test_unusable_names_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidProjectNameError) as rejected:
        normalize_name(raw)

    assert rejected.value.code == "PROJECT_NAME_INVALID"
    assert rejected.value.details == {"field": "name", "max_chars": 80}


def test_a_decomposed_name_is_measured_after_normalization() -> None:
    decomposed = "é" * MAX_NAME_CHARS

    assert len(normalize_name(decomposed)) == MAX_NAME_CHARS

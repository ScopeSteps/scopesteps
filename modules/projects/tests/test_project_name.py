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
        ("Cafe\u0301 menu", "Caf\u00e9 menu"),
    ],
)
def test_names_are_stored_trimmed_and_normalized(raw: str, stored: str) -> None:
    assert normalize_name(raw) == stored


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "\t\n",
        "\u200b",
        "n" * (MAX_NAME_CHARS + 1),
        "Room\x00booking",
        "Room\u202ebooking",
        "Room\u200bbooking",
    ],
    ids=[
        "empty",
        "spaces",
        "tabs",
        "zero-width-only",
        "too-long",
        "control-character",
        "direction-override",
        "zero-width-inside",
    ],
)
def test_unusable_names_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidProjectNameError) as rejected:
        normalize_name(raw)

    assert rejected.value.code == "PROJECT_NAME_INVALID"
    assert rejected.value.details == {"field": "name", "max_chars": 80}


def test_a_decomposed_name_is_measured_after_normalization() -> None:
    decomposed = "e\u0301" * MAX_NAME_CHARS

    assert len(normalize_name(decomposed)) == MAX_NAME_CHARS

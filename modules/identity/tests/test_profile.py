import pytest

from scopesteps.identity.domain.profile import (
    InvalidProfileError,
    Profile,
    normalize_profile,
)


def test_names_are_nfc_and_collapsed_and_about_keeps_its_line_breaks() -> None:
    profile = normalize_profile("  José  Lee ", "\tLead\n designer ", "Line one\r\n\nLine two ")

    assert profile == Profile(
        display_name="José Lee", job_title="Lead designer", about="Line one\n\nLine two"
    )


def test_the_job_title_and_about_may_be_empty() -> None:
    assert normalize_profile("Dana", "", "") == Profile("Dana", "", "")


@pytest.mark.parametrize(
    ("display_name", "job_title", "about", "field"),
    [
        ("", "", "", "display_name"),
        ("n" * 61, "", "", "display_name"),
        ("Dana", "Lead‮designer", "", "job_title"),
        ("Dana", "", "Tab\there", "about"),
    ],
    ids=["blank-name", "long-name", "direction-override", "tab-in-about"],
)
def test_invalid_fields_name_the_field(
    display_name: str, job_title: str, about: str, field: str
) -> None:
    with pytest.raises(InvalidProfileError) as raised:
        normalize_profile(display_name, job_title, about)

    assert raised.value.details["field"] == field

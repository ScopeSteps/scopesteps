from pathlib import Path

import pytest
from pydantic import ValidationError

from scopesteps.api.settings import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sources,backlog", ["sources", "backlog"]),
        (" sources , backlog ,", ["sources", "backlog"]),
        ("", []),
    ],
)
def test_enabled_modules_parses_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str, expected: list[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENABLED_MODULES", raw)

    assert Settings().enabled_modules == expected


def test_enabled_modules_rejects_unknown_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENABLED_MODULES", "sources,billing")

    with pytest.raises(ValidationError, match="billing"):
        Settings()

from pathlib import Path

import pytest

from scopesteps.api.local_env import SEED_SETTING, ensure_seed_password, main, sets_local_auth
from scopesteps.api.settings import Settings


@pytest.fixture(autouse=True)
def no_password_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SEED_SETTING, raising=False)


def password_lines(env_file: Path) -> list[str]:
    return [
        line for line in env_file.read_text().splitlines() if line.startswith(f"{SEED_SETTING}=")
    ]


@pytest.mark.parametrize(
    "content",
    [
        "APP_ENV=local\nSEED_ACCOUNT_PASSWORD=\nMODEL_PROVIDER=none\n",
        "APP_ENV=local\nSEED_ACCOUNT_PASSWORD=''\n",
        "APP_ENV=local\n",
    ],
)
def test_a_missing_or_empty_password_is_generated_once(tmp_path: Path, content: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(content)

    written = ensure_seed_password(env_file)
    first = env_file.read_text()
    written_again = ensure_seed_password(env_file)

    assert (written, written_again) == (True, False)
    assert env_file.read_text() == first
    assert len(password_lines(env_file)) == 1
    assert "APP_ENV=local" in first
    password = Settings(_env_file=env_file).seed_account_password  # pyright: ignore[reportCallIssue]
    assert password is not None
    assert len(password.get_secret_value()) >= 12


def test_a_password_the_developer_chose_is_kept(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    content = "SEED_ACCOUNT_PASSWORD=chosen-by-the-developer\n"
    env_file.write_text(content)

    assert ensure_seed_password(env_file) is False
    assert env_file.read_text() == content


def test_a_password_in_the_environment_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SEED_ACCOUNT_PASSWORD=\n")
    monkeypatch.setenv(SEED_SETTING, "set-for-this-shell-only")

    assert ensure_seed_password(env_file) is False
    assert env_file.read_text() == "SEED_ACCOUNT_PASSWORD=\n"


def test_each_checkout_gets_its_own_password(tmp_path: Path) -> None:
    first, second = tmp_path / "first.env", tmp_path / "second.env"
    for env_file in (first, second):
        env_file.write_text("SEED_ACCOUNT_PASSWORD=\n")
        ensure_seed_password(env_file)

    assert password_lines(first) != password_lines(second)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("AUTH_MODE=local\n", True),
        ("AUTH_MODE='local'\n", True),
        ("AUTH_MODE=session\n", False),
        ("# AUTH_MODE=local\n", False),
        ("APP_ENV=local\n", False),
    ],
)
def test_an_explicit_local_auth_mode_is_recognised(
    tmp_path: Path, content: str, expected: bool
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(content)

    assert sets_local_auth(env_file) is expected


def test_the_command_names_the_accounts_but_never_prints_the_password(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_MODE=local\nSEED_ACCOUNT_PASSWORD=\n")

    main()

    output = capsys.readouterr().out
    [line] = password_lines(env_file)
    assert line.split("=", 1)[1] not in output
    assert "editor@scopesteps.local" in output
    assert "AUTH_MODE=local" in output


def test_the_command_refuses_to_run_without_an_env_file() -> None:
    with pytest.raises(SystemExit, match=r"Copy \.env\.example"):
        main()

"""Gives the seeded accounts a password of this machine's own in the local `.env`.

`.env.example` ships `SEED_ACCOUNT_PASSWORD` empty so no password is committed (ADR 0007);
`just setup` runs this so a fresh checkout still has accounts that can sign in.
"""

import os
import re
import secrets
import sys
from pathlib import Path

SEED_SETTING = "SEED_ACCOUNT_PASSWORD"
_ASSIGNMENT = re.compile(rf"^\s*{SEED_SETTING}\s*=(?P<value>.*)$")
_LOCAL_AUTH = re.compile(r"^\s*AUTH_MODE\s*=\s*['\"]?local['\"]?\s*$", re.MULTILINE)


def ensure_seed_password(env_file: Path) -> bool:
    """Write a random password into `env_file` unless it already sets one.

    Returns whether it wrote one. A value already in the file or the environment is kept.
    """
    if os.environ.get(SEED_SETTING, "").strip():
        return False
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assignment = f"{SEED_SETTING}={secrets.token_urlsafe(18)}"
    for index, line in enumerate(lines):
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        if match.group("value").strip().strip("'\""):
            return False
        lines[index] = assignment
        break
    else:
        lines.append(assignment)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def sets_local_auth(env_file: Path) -> bool:
    return _LOCAL_AUTH.search(env_file.read_text(encoding="utf-8")) is not None


def main() -> None:
    env_file = Path(".env")
    if not env_file.is_file():
        sys.exit("No .env here. Copy .env.example to .env first (`just setup` does).")
    if ensure_seed_password(env_file):
        sys.stdout.write(
            f"Generated {SEED_SETTING} in .env. Sign in as viewer@scopesteps.local, "
            "editor@scopesteps.local or approver@scopesteps.local with it.\n"
        )
    if sets_local_auth(env_file):
        sys.stdout.write(
            ".env sets AUTH_MODE=local, so the app acts as the Local Reviewer and sign-in is "
            "disabled. Remove that line to sign in.\n"
        )


if __name__ == "__main__":
    main()

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_FRONTEND_VARIABLES = {"VITE_API_BASE_URL"}


def _example_variables() -> set[str]:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    return {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}


def test_only_allowlisted_variables_are_exposed_to_the_browser() -> None:
    exposed = {name for name in _example_variables() if name.startswith("VITE_")}

    assert exposed <= PUBLIC_FRONTEND_VARIABLES


def test_real_environment_files_and_databases_are_git_ignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text().splitlines()

    assert {".env", ".env.*", "!.env.example", "var/", "*.db"} <= set(ignored)

"""API messages people read say "approved version" and "proposed version", never "baseline" or
"candidate" (docs/product/glossary.md). Field names, enum values and prompts keep their names."""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INTERNAL = re.compile(r"\b(baselines?|candidates?)\b", re.IGNORECASE)
# Where a message a person reads is written: an error's text, an activity summary, chat text.
MESSAGE_KEYWORDS = frozenset({"summary", "message", "text"})


def _text(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "{}"
            for part in node.values
        )
    return None


def _is_error(call: ast.Call) -> bool:
    name = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
    return name.endswith("Error")


def messages(source: str) -> list[str]:
    """The texts in `source` a person can read: error arguments, message keywords and `text`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            values = [*node.args] if _is_error(node) else []
            values += [kw.value for kw in node.keywords if kw.arg in MESSAGE_KEYWORDS]
            found += [text for value in values if (text := _text(value)) is not None]
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "text" for target in node.targets
        ):
            text = _text(node.value)
            if text is not None:
                found.append(text)
    return found


def test_the_check_finds_the_words_in_messages_and_nowhere_else() -> None:
    sample = """
CANDIDATE_STATE = "candidate_in_review"
raise RunStateError("This candidate is gone")
audit.record(summary=f"Approved baseline v{number}", kind="baseline")
text = f"CR-{number} kept the baseline."
"""

    flagged = sorted(text for text in messages(sample) if INTERNAL.search(text))

    assert flagged == [
        "Approved baseline v{}",
        "CR-{} kept the baseline.",
        "This candidate is gone",
    ]


def test_no_api_message_says_baseline_or_candidate() -> None:
    files = [
        path
        for root in (REPO_ROOT / "modules", REPO_ROOT / "apps" / "api" / "src")
        for path in root.rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts
    ]
    offending = [
        f"{path.relative_to(REPO_ROOT)}: {text}"
        for path in files
        for text in messages(path.read_text())
        if INTERNAL.search(text)
    ]

    assert len(files) > 100
    assert offending == []

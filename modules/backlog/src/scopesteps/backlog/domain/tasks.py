"""Whether a task stays inside its story's scope, checked by code on every read.

A task says how to do its story; it must never bring in new work. The check is deliberately
simple and explainable: it compares the task's words with its story's (title, description and
criteria) and with the work the version leaves out of scope. It flags, it never removes: a
person reads the reason and decides.
"""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

from scopesteps.backlog.domain.ids import TaskId
from scopesteps.backlog.domain.version import (
    MAX_TASKS_PER_STORY,
    MAX_TITLE_CHARS,
    Item,
    ScopeNote,
    Task,
)

TaskFlagCode = Literal["out_of_scope_work", "not_in_story"]

# Words that name how work is done rather than what is built, so a task may use them whether or
# not its story does ("Write tests for the overlap check").
_HOW_WORDS = frozenset(
    [
        "add",
        "api",
        "app",
        "backend",
        "build",
        "button",
        "change",
        "check",
        "code",
        "component",
        "config",
        "configure",
        "copy",
        "create",
        "data",
        "database",
        "deploy",
        "design",
        "display",
        "doc",
        "document",
        "docs",
        "draft",
        "edit",
        "email",
        "endpoint",
        "error",
        "field",
        "fix",
        "flow",
        "form",
        "frontend",
        "handle",
        "implement",
        "integration",
        "layout",
        "list",
        "load",
        "log",
        "logic",
        "make",
        "message",
        "migration",
        "model",
        "page",
        "prepare",
        "query",
        "review",
        "rule",
        "save",
        "schema",
        "screen",
        "script",
        "set",
        "setup",
        "show",
        "store",
        "style",
        "support",
        "table",
        "test",
        "text",
        "update",
        "validate",
        "validation",
        "view",
        "wire",
        "write",
    ]
)

_STOP_WORDS = frozenset(
    [
        "about",
        "after",
        "all",
        "also",
        "and",
        "any",
        "are",
        "been",
        "before",
        "but",
        "can",
        "each",
        "for",
        "from",
        "has",
        "have",
        "how",
        "into",
        "its",
        "not",
        "one",
        "only",
        "other",
        "our",
        "out",
        "per",
        "should",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "use",
        "used",
        "user",
        "users",
        "using",
        "via",
        "was",
        "way",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "within",
        "without",
        "you",
        "your",
    ]
)

_WORD = re.compile(r"[a-z0-9]+")

# Shorter stems match too much by accident.
_MIN_STEM = 3
_ENDINGS = frozenset(
    [
        "s",
        "es",
        "d",
        "ed",
        "er",
        "ers",
        "ing",
        "ings",
        "ion",
        "ions",
        "ation",
        "ations",
        "ment",
        "ments",
        "able",
        "ability",
        "ly",
        "ling",
        "lation",
    ]
)


@dataclass(frozen=True)
class TaskFlag:
    code: TaskFlagCode
    message: str
    """Plain words for the person reviewing the task, naming what it brings in."""


def task_flag(story: Item, task: Task, out_of_scope: Iterable[ScopeNote]) -> TaskFlag | None:
    """Why `task` looks like work its story does not cover, or None when it looks in scope.

    Work the version leaves out of scope is flagged first, by the note it matches. Otherwise a
    task is flagged when none of its words, other than how-to words, appear in its story.
    """
    story_words = _words(story.title, story.description, *(c.text for c in story.criteria))
    task_words = _words(task.title)
    for note in out_of_scope:
        excluded = _words(note.summary) - _HOW_WORDS
        brought_in = sorted(
            word
            for word in task_words
            if _matches_any(word, excluded) and not _matches_any(word, story_words)
        )
        if brought_in:
            return TaskFlag(
                "out_of_scope_work",
                f"Mentions work left out of scope ({', '.join(brought_in)}): “{note.summary}”",
            )
    content = task_words - _HOW_WORDS
    if content and not any(_matches_any(word, story_words) for word in content):
        return TaskFlag(
            "not_in_story",
            f"Its story does not mention {_listed(sorted(content))}. A task should only say "
            "how to do its story.",
        )
    return None


def with_suggested_tasks(
    story: Item, titles: Sequence[str], new_id: Callable[[], UUID]
) -> tuple[Item, int]:
    """The story with the agent's new suggestions in place of the ones nobody has reviewed yet,
    and how many were added. Tasks a person wrote or accepted stay first, as they are; a
    suggestion that repeats one of them, or is empty or too long, is dropped, and nothing goes
    past the story's task limit."""
    kept = [task for task in story.tasks if task.suggestion != "pending"]
    seen = {task.title.casefold() for task in kept}
    added: list[Task] = []
    for raw in titles:
        title = " ".join(raw.split())
        if not title or len(title) > MAX_TITLE_CHARS or title.casefold() in seen:
            continue
        if len(kept) + len(added) >= MAX_TASKS_PER_STORY:
            break
        seen.add(title.casefold())
        added.append(Task(TaskId(new_id()), title, "suggested", "pending"))
    return replace(story, tasks=(*kept, *added)), len(added)


def _words(*texts: str) -> frozenset[str]:
    return frozenset(
        _singular(word)
        for text in texts
        for word in _WORD.findall(text.lower())
        if len(word) >= 3 and word not in _STOP_WORDS and not word.isdigit()
    )


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _matches_any(word: str, others: frozenset[str]) -> bool:
    """The same word, or one is the other plus an ending."""
    return word in others or any(_shares_stem(word, other) for other in others)


def _shares_stem(first: str, second: str) -> bool:
    """One word is the other with an ending: "book" and "booking", "cancel" and "cancelled",
    "overlap" and "overlapping", "validate" and "validation"; never "room" and "roommate"."""
    shorter, longer = sorted((first, second), key=len)
    stems = {shorter, shorter[:-1]} if shorter.endswith("e") else {shorter}
    for stem in stems:
        if len(stem) < _MIN_STEM or not longer.startswith(stem):
            continue
        ending = longer[len(stem) :]
        # A doubled last consonant before the ending: "overlap" + "p" + "ing".
        if ending in _ENDINGS or (ending[:1] == stem[-1] and ending[1:] in _ENDINGS):
            return True
    return False


def _listed(words: list[str]) -> str:
    quoted = [f"“{word}”" for word in words[:4]]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " or " + quoted[-1]

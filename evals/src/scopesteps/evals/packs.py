"""Load evaluation packs and check them against their own source files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from scopesteps.evals.annotations import (
    INITIAL_SOURCE_FILES,
    MAX_REVIEWER_TEXT_CHARS,
    AnnotationFile,
    AnswerFile,
    SourceFile,
)
from scopesteps.sources.client import TextBlock, split_into_blocks

DATASETS_DIR = Path(__file__).resolve().parents[3] / "datasets"

Split = Literal["dev", "heldout"]

# Proposed POC limits (POC Implementation Plan, section 2).
MAX_SOURCE_BYTES = 512 * 1024
MAX_INITIAL_WORDS = 6000

PACK_FILES = (
    "brief.md",
    "transcript.md",
    "change_request.txt",
    "annotations.yaml",
    "clarification_answers.yaml",
)


class PackError(Exception):
    def __init__(self, pack_dir: Path, problems: list[str]) -> None:
        super().__init__(f"{pack_dir.name}: " + "; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Pack:
    split: Split
    path: Path
    annotations: AnnotationFile
    answers: AnswerFile
    blocks: dict[SourceFile, list[TextBlock]]

    @property
    def id(self) -> str:
        return self.annotations.pack.id

    def source_text(self, file: SourceFile) -> str:
        return (self.path / file).read_text(encoding="utf-8")


def pack_dirs(split: Split, root: Path = DATASETS_DIR) -> list[Path]:
    split_dir = root / split
    if not split_dir.is_dir():
        return []
    return sorted(path for path in split_dir.iterdir() if path.is_dir())


def load_pack(pack_dir: Path, split: Split) -> Pack:
    """Load one pack, raising PackError listing every problem found."""
    missing = [name for name in PACK_FILES if not (pack_dir / name).is_file()]
    if missing:
        raise PackError(pack_dir, [f"missing {name}" for name in missing])

    problems: list[str] = []
    blocks: dict[SourceFile, list[TextBlock]] = {}
    initial_words = 0
    for file in ("brief.md", "transcript.md", "change_request.txt"):
        raw = (pack_dir / file).read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            problems.append(f"{file} exceeds {MAX_SOURCE_BYTES} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{file} is not UTF-8")
            continue
        blocks[file] = split_into_blocks(text)
        if file in INITIAL_SOURCE_FILES:
            initial_words += len(text.split())
        elif len(text.strip()) > MAX_REVIEWER_TEXT_CHARS:
            problems.append(f"{file} exceeds {MAX_REVIEWER_TEXT_CHARS} characters")
    if initial_words > MAX_INITIAL_WORDS:
        problems.append(
            f"brief and transcript total {initial_words} words (max {MAX_INITIAL_WORDS})"
        )

    try:
        annotations = AnnotationFile.model_validate(_read_yaml(pack_dir / "annotations.yaml"))
        answers = AnswerFile.model_validate(_read_yaml(pack_dir / "clarification_answers.yaml"))
    except (ValidationError, yaml.YAMLError) as error:
        raise PackError(pack_dir, [*problems, str(error)]) from error

    if annotations.pack.id != pack_dir.name:
        problems.append(f"pack id {annotations.pack.id!r} does not match folder name")
    problems += _evidence_problems(annotations, blocks)
    problems += _answer_problems(annotations, answers)
    if problems:
        raise PackError(pack_dir, problems)
    return Pack(split, pack_dir, annotations, answers, blocks)


def load_packs(split: Split, root: Path = DATASETS_DIR) -> list[Pack]:
    return [load_pack(path, split) for path in pack_dirs(split, root)]


def _read_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _evidence_problems(
    annotations: AnnotationFile, blocks: dict[SourceFile, list[TextBlock]]
) -> list[str]:
    problems: list[str] = []
    for annotation in annotations.annotations:
        for evidence in annotation.evidence:
            paragraphs = blocks.get(evidence.file, [])
            if evidence.paragraph > len(paragraphs):
                problems.append(
                    f"{annotation.id}: {evidence.file} has no paragraph {evidence.paragraph}"
                )
            elif evidence.quote not in paragraphs[evidence.paragraph - 1].text:
                problems.append(
                    f"{annotation.id}: quote not found in {evidence.file} "
                    f"paragraph {evidence.paragraph}: {evidence.quote!r}"
                )
    return problems


def _answer_problems(annotations: AnnotationFile, answers: AnswerFile) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for answer in answers.answers:
        target = annotations.get(answer.question_for)
        if target is None:
            problems.append(f"answer for unknown annotation {answer.question_for}")
        elif target.expect != "ask":
            problems.append(f"answer for {answer.question_for}, which does not expect a question")
        if answer.question_for in seen:
            problems.append(f"more than one answer for {answer.question_for}")
        seen.add(answer.question_for)
    return problems

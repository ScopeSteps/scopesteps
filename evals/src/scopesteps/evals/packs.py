"""Load evaluation packs and check them against their own source files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from scopesteps.evals.annotations import (
    MAX_REVIEWER_TEXT_CHARS,
    AnnotationFile,
    AnswerFile,
    Evidence,
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
CHANGE_REQUEST_FILE = "change_request.txt"
# Optional extra initial sources, uploaded as supporting documents: supporting-<name>.md or .txt.
SUPPORTING_PREFIX = "supporting-"
SUPPORTING_SUFFIXES = (".md", ".txt")


def initial_source_files(pack_dir: Path) -> tuple[str, ...]:
    """The pack's initial sources in the order runs number their paragraphs: the brief, the
    transcript, then any supporting documents by name."""
    supporting = sorted(
        path.name
        for path in pack_dir.iterdir()
        if path.is_file()
        and path.name.startswith(SUPPORTING_PREFIX)
        and path.suffix in SUPPORTING_SUFFIXES
    )
    return ("brief.md", "transcript.md", *supporting)


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
    initial_files: tuple[SourceFile, ...]

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
    initial_files = initial_source_files(pack_dir)
    initial_words = 0
    for file in (*initial_files, CHANGE_REQUEST_FILE):
        raw = (pack_dir / file).read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            problems.append(f"{file} exceeds {MAX_SOURCE_BYTES} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{file} is not UTF-8")
            continue
        blocks[file] = split_into_blocks(text)
        if file in initial_files:
            initial_words += len(text.split())
        elif len(text.strip()) > MAX_REVIEWER_TEXT_CHARS:
            problems.append(f"{file} exceeds {MAX_REVIEWER_TEXT_CHARS} characters")
    if initial_words > MAX_INITIAL_WORDS:
        problems.append(f"initial sources total {initial_words} words (max {MAX_INITIAL_WORDS})")

    try:
        annotations = AnnotationFile.model_validate(_read_yaml(pack_dir / "annotations.yaml"))
        answers = AnswerFile.model_validate(_read_yaml(pack_dir / "clarification_answers.yaml"))
    except (ValidationError, yaml.YAMLError) as error:
        raise PackError(pack_dir, [*problems, str(error)]) from error

    if annotations.pack.id != pack_dir.name:
        problems.append(f"pack id {annotations.pack.id!r} does not match folder name")
    problems += _evidence_problems(annotations, blocks)
    problems += _people_problems(annotations, blocks)
    problems += _answer_problems(annotations, answers)
    if problems:
        raise PackError(pack_dir, problems)
    return Pack(split, pack_dir, annotations, answers, blocks, initial_files)


def load_packs(split: Split, root: Path = DATASETS_DIR) -> list[Pack]:
    return [load_pack(path, split) for path in pack_dirs(split, root)]


def _read_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _evidence_problems(
    annotations: AnnotationFile, blocks: dict[SourceFile, list[TextBlock]]
) -> list[str]:
    return [
        problem
        for annotation in annotations.annotations
        for problem in _quote_problems(annotation.id, annotation.evidence, blocks)
    ]


def _quote_problems(
    owner: str, cited: list[Evidence], blocks: dict[SourceFile, list[TextBlock]]
) -> list[str]:
    problems: list[str] = []
    for evidence in cited:
        paragraphs = blocks.get(evidence.file)
        if paragraphs is None:
            problems.append(f"{owner}: {evidence.file} is not a source file of this pack")
        elif evidence.paragraph > len(paragraphs):
            problems.append(f"{owner}: {evidence.file} has no paragraph {evidence.paragraph}")
        elif evidence.quote not in paragraphs[evidence.paragraph - 1].text:
            problems.append(
                f"{owner}: quote not found in {evidence.file} "
                f"paragraph {evidence.paragraph}: {evidence.quote!r}"
            )
    return problems


def _people_problems(
    annotations: AnnotationFile, blocks: dict[SourceFile, list[TextBlock]]
) -> list[str]:
    """Every expected person is quoted from, and named in, a paragraph of the initial sources."""
    problems: list[str] = []
    for person in annotations.people:
        cited = [*person.evidence, *person.rights_evidence]
        faults = _quote_problems(person.name, cited, blocks)
        problems += faults
        if not faults and not any(
            person.name in blocks[e.file][e.paragraph - 1].text for e in person.evidence
        ):
            problems.append(f"{person.name}: no evidence paragraph contains the name")
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

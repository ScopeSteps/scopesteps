"""Load evaluation packs and check them against their own source files."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ValidationError

from scopesteps.agent.client import SpeakerNote
from scopesteps.evals.annotations import (
    MAX_REVIEWER_TEXT_CHARS,
    AnnotationFile,
    AnswerFile,
    Evidence,
    ReplyQuestionFile,
    SourceFile,
    SpeakerFile,
)
from scopesteps.projects.client import name_key
from scopesteps.sources.client import (
    TextBlock,
    detect_speakers,
    speakers_by_paragraph,
    split_into_blocks,
)

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
# Optional, so packs frozen before the conversation existed stay valid; they are not scored on
# replies.
REPLY_QUESTIONS_FILE = "reply_questions.yaml"
# Optional, so packs frozen before speakers were confirmed stay valid; their speakers reach runs
# as "role unknown", as unconfirmed speakers do in the app.
SPEAKERS_FILE = "speakers.yaml"
TRANSCRIPT_FILE = "transcript.md"
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
    replies: ReplyQuestionFile | None = None
    speakers: SpeakerFile | None = None
    notes: dict[tuple[SourceFile, int], tuple[SpeakerNote, ...]] = field(
        default_factory=dict[tuple[SourceFile, int], tuple[SpeakerNote, ...]]
    )
    """Who speaks in each transcript paragraph, by file and paragraph number, as the app would
    show it to the agent: labels found by the sources parser, identities from `speakers`."""

    @property
    def id(self) -> str:
        return self.annotations.pack.id

    def source_text(self, file: SourceFile) -> str:
        return (self.path / file).read_text(encoding="utf-8")


def pack_dirs(split: Split, root: Path = DATASETS_DIR) -> list[Path]:
    split_dir = root / split
    if not split_dir.is_dir():
        return []
    # Hidden folders are not packs: held-out packs are a git clone with its own .git.
    return sorted(
        path for path in split_dir.iterdir() if path.is_dir() and not path.name.startswith(".")
    )


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
        replies_path = pack_dir / REPLY_QUESTIONS_FILE
        replies = (
            ReplyQuestionFile.model_validate(_read_yaml(replies_path))
            if replies_path.is_file()
            else None
        )
        speakers_path = pack_dir / SPEAKERS_FILE
        speakers = (
            SpeakerFile.model_validate(_read_yaml(speakers_path))
            if speakers_path.is_file()
            else None
        )
    except (ValidationError, yaml.YAMLError) as error:
        raise PackError(pack_dir, [*problems, str(error)]) from error

    if annotations.pack.id != pack_dir.name:
        problems.append(f"pack id {annotations.pack.id!r} does not match folder name")
    transcript = (pack_dir / TRANSCRIPT_FILE).read_text(encoding="utf-8")
    notes = _speaker_notes(transcript, speakers)
    problems += _speaker_problems(transcript, speakers)
    problems += _evidence_problems(annotations, blocks)
    problems += _people_problems(annotations, blocks, notes)
    problems += _answer_problems(annotations, answers)
    if replies is not None:
        problems += _reply_problems(replies, annotations, answers, blocks)
    if problems:
        raise PackError(pack_dir, problems)
    return Pack(
        split, pack_dir, annotations, answers, blocks, initial_files, replies, speakers, notes
    )


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


def _speaker_notes(
    transcript: str, speakers: SpeakerFile | None
) -> dict[tuple[SourceFile, int], tuple[SpeakerNote, ...]]:
    labels = {speaker.key: speaker.label for speaker in detect_speakers(transcript)}
    confirmed = {name_key(s.label): s for s in speakers.speakers} if speakers else {}

    def note(key: str) -> SpeakerNote:
        label = labels.get(key, key)
        found = confirmed.get(key)
        if found is None:
            return SpeakerNote(label)
        if found.not_a_person:
            return SpeakerNote(label, not_a_person=True)
        return SpeakerNote(label, found.name, found.meeting_role)

    return {
        (TRANSCRIPT_FILE, ordinal): tuple(note(key) for key in keys)
        for ordinal, keys in speakers_by_paragraph(transcript).items()
    }


def _speaker_problems(transcript: str, speakers: SpeakerFile | None) -> list[str]:
    """A pack's mapping answers for exactly the labels the sources parser finds, as a user who
    went through Who's who would have."""
    if speakers is None:
        return []
    detected = {speaker.key for speaker in detect_speakers(transcript)}
    mapped = {name_key(speaker.label) for speaker in speakers.speakers}
    return [
        *(
            f"{SPEAKERS_FILE}: no speaker {key!r} in the transcript"
            for key in sorted(mapped - detected)
        ),
        *(
            f"{SPEAKERS_FILE}: speaker {key!r} is not confirmed"
            for key in sorted(detected - mapped)
        ),
    ]


def _people_problems(
    annotations: AnnotationFile,
    blocks: dict[SourceFile, list[TextBlock]],
    notes: dict[tuple[SourceFile, int], tuple[SpeakerNote, ...]],
) -> list[str]:
    """Every expected person is quoted from, and named in, a paragraph of the initial sources:
    in its text, or as a speaker in it confirmed under that name."""
    problems: list[str] = []
    for person in annotations.people:
        cited = [*person.evidence, *person.rights_evidence]
        faults = _quote_problems(person.name, cited, blocks)
        problems += faults
        if not faults and not any(
            person.name in blocks[e.file][e.paragraph - 1].text
            or any(note.name == person.name for note in notes.get((e.file, e.paragraph), ()))
            for e in person.evidence
        ):
            problems.append(f"{person.name}: no evidence paragraph names them")
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


def _reply_problems(
    replies: ReplyQuestionFile,
    annotations: AnnotationFile,
    answers: AnswerFile,
    blocks: dict[SourceFile, list[TextBlock]],
) -> list[str]:
    """Quotes hold, and `answer_for` names an initial decision the reviewer answered."""
    answered = {a.question_for for a in answers.answers if a.answer is not None}
    problems: list[str] = []
    for question in replies.questions:
        problems += _quote_problems(question.id, question.evidence, blocks)
        if question.answer_for is None:
            continue
        target = annotations.get(question.answer_for)
        if target is None or target.phase != "initial" or question.answer_for not in answered:
            problems.append(
                f"{question.id}: answer_for {question.answer_for} is not an answered initial "
                "decision"
            )
    return problems

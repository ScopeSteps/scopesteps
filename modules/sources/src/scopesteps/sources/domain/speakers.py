"""Speaker labels in a meeting transcript, found by rule rather than by a model.

Transcript exports label each turn with the speaker's name in a fixed format, so a parser is
exact, free and testable, and sends nothing to a model. It never guesses who a speaker is or what
their role is; people confirm that (ADR 0012).
"""

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from scopesteps.projects.client import name_key
from scopesteps.sources.domain.blocks import split_into_blocks
from scopesteps.sources.domain.ids import SourceVersionId
from scopesteps.sources.domain.source import SourceBlock, SpeakerLabel

# Longer labels are sentences that happen to contain a colon ("Note pasted into the chat by a
# participant: ..."), not names.
MAX_LABEL_WORDS = 5
MAX_LABEL_CHARS = 60
# Case folding can lengthen a name (ß becomes ss), by at most three characters per character.
MAX_LABEL_KEY_CHARS = 3 * MAX_LABEL_CHARS
# Enough of the first turn to recognise the speaker by, without returning the whole turn.
MAX_SAMPLE_CHARS = 160

# Words that start a heading or a note rather than a name ("Agenda:", "Action items:").
STOP_WORDS = frozenset(
    {
        "a",
        "action",
        "actions",
        "agenda",
        "answer",
        "apologies",
        "attendees",
        "background",
        "chat",
        "comment",
        "conclusion",
        "context",
        "date",
        "decision",
        "decisions",
        "edit",
        "example",
        "follow-up",
        "goal",
        "goals",
        "important",
        "issue",
        "issues",
        "item",
        "items",
        "kickoff",
        "link",
        "location",
        "meeting",
        "minutes",
        "next",
        "note",
        "notes",
        "objective",
        "outcome",
        "owner",
        "participants",
        "present",
        "purpose",
        "q",
        "question",
        "questions",
        "re",
        "recap",
        "recording",
        "reminder",
        "risk",
        "risks",
        "scope",
        "status",
        "subject",
        "summary",
        "time",
        "tip",
        "title",
        "todo",
        "topic",
        "transcript",
        "update",
        "warning",
        "webvtt",
    }
)

_TIME = r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"
# A line that is only a time, a cue timing ("00:00:01.000 --> 00:00:04.000") or a cue number.
_TIMESTAMP_LINE = re.compile(rf"^(?:\[?\(?{_TIME}\)?\]?(?:\s*-->\s*{_TIME}.*)?|\d+|WEBVTT.*)$")
_LEADING_TIME = re.compile(rf"^[\[(]?{_TIME}[\])]?\s*(?:[-\u2013\u2014]\s*)?")
_VOICE = re.compile(r"^<v(?:\.[\w-]+)*\s+(?P<label>[^>]+)>(?P<rest>.*)$")
_HEADER = re.compile(rf"^(?P<label>.+?)\s+{_TIME}$")
_BOLD_INSIDE = re.compile(r"^\*\*(?P<label>[^*]+?)\s*:\s*\*\*\s*(?P<rest>.*)$")
_BOLD_OUTSIDE = re.compile(r"^\*\*(?P<label>[^*]+?)\*\*\s*:\s*(?P<rest>.*)$")
_PLAIN = re.compile(r"^(?P<label>[^:]+?)\s*:(?:\s+(?P<rest>.*))?$")
_ROLE = re.compile(r"^(?P<name>.+?)\s*\([^()]*\)$")
_NAME = re.compile("^\\w[\\w .'\u2019-]*$")
_VOICE_END = re.compile(r"</v>\s*$")


@dataclass(frozen=True)
class DetectedSpeaker:
    """A distinct speaker label, in order of first appearance.

    `key` is the label in `name_key` form, which is how labels and participants are matched.
    A turn runs until another speaker's label, so consecutive labels by one speaker are one turn.
    `sample` is the start of the speaker's first turn, as plain text.
    """

    label: str
    key: str
    turn_count: int
    first_block_ordinal: int
    sample: str


@dataclass(frozen=True)
class _Label:
    label: str
    rest: str
    # A header ("Mira Holt   0:03", "<v Mira Holt>") may stand alone with the turn on the next
    # lines; an inline label carries the turn on its own line.
    inline: bool


def detect_speakers(text: str) -> list[DetectedSpeaker]:
    """Every distinct speaker label in a transcript, with how often they take a turn.

    Recognises `Name:`, `**Name:**`, `**Name**:`, `Name (Role):` (the role is dropped), Teams VTT
    `<v Name>` and Teams text `Name   0:03` lines, each optionally after a timestamp. A colon label
    counts only where a turn can start: the first line of a paragraph, or the line after a
    timestamp or another inline turn. Labels longer than five words or 60 characters, labels that
    are not name-like and labels that start with a heading word (`Note`, `Agenda`, ...) are not
    speakers.
    """
    speakers: dict[str, DetectedSpeaker] = {}
    previous_key: str | None = None
    awaiting_sample: str | None = None
    for block in split_into_blocks(text):
        turn_can_start = True
        for raw_line in block.text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if _TIMESTAMP_LINE.match(line):
                turn_can_start = True
                continue
            found = _label_in(line, turn_can_start)
            if found is None:
                if awaiting_sample is not None:
                    _set_sample(speakers, awaiting_sample, line)
                    awaiting_sample = None
                turn_can_start = False
                continue
            key = name_key(found.label)
            known = speakers.get(key)
            if known is None:
                speakers[key] = DetectedSpeaker(
                    label=found.label,
                    key=key,
                    turn_count=1,
                    first_block_ordinal=block.ordinal,
                    sample="",
                )
            elif key != previous_key:
                speakers[key] = replace(known, turn_count=known.turn_count + 1)
            previous_key = key
            awaiting_sample = key if not speakers[key].sample else None
            if found.rest and awaiting_sample is not None:
                _set_sample(speakers, key, found.rest)
                awaiting_sample = None
            turn_can_start = found.inline
    return list(speakers.values())


def speaker_labels(
    version_id: SourceVersionId, text: str, blocks: Sequence[SourceBlock]
) -> list[SpeakerLabel]:
    """The labels in a stored version's text, each pointing at the block of its first turn.

    `blocks` must be the version's blocks, split from the same text.
    """
    block_ids = {block.ordinal: block.id for block in blocks}
    return [
        SpeakerLabel(
            source_version_id=version_id,
            label=speaker.label,
            key=speaker.key,
            turn_count=speaker.turn_count,
            first_block_id=block_ids[speaker.first_block_ordinal],
            first_block_ordinal=speaker.first_block_ordinal,
            sample=speaker.sample,
        )
        for speaker in detect_speakers(text)
    ]


def _label_in(line: str, turn_can_start: bool) -> _Label | None:
    voice = _VOICE.match(line)
    if voice:
        label = _speaker_name(html.unescape(voice["label"]))
        rest = _VOICE_END.sub("", voice["rest"]).strip()
        return None if label is None else _Label(label, rest, inline=True)
    if not turn_can_start:
        return None
    line = _LEADING_TIME.sub("", line)
    header = _HEADER.match(line)
    if header:
        label = _speaker_name(header["label"])
        return None if label is None else _Label(label, "", inline=False)
    for pattern in (_BOLD_INSIDE, _BOLD_OUTSIDE, _PLAIN):
        match = pattern.match(line)
        if match:
            label = _speaker_name(match["label"])
            rest = (match["rest"] or "").strip()
            return None if label is None else _Label(label, rest, inline=bool(rest))
    return None


def _speaker_name(label: str) -> str | None:
    """The name in a label, or None when the label is not a speaker's."""
    label = " ".join(label.split())
    role = _ROLE.match(label)
    if role:
        label = role["name"]
    words = label.split()
    if (
        not words
        or len(words) > MAX_LABEL_WORDS
        or len(label) > MAX_LABEL_CHARS
        or not _NAME.match(label)
        or not any(character.isalpha() for character in label)
        or name_key(words[0]) in STOP_WORDS
    ):
        return None
    return label


def _set_sample(speakers: dict[str, DetectedSpeaker], key: str, text: str) -> None:
    sample = " ".join(text.split())
    if len(sample) > MAX_SAMPLE_CHARS:
        sample = sample[: MAX_SAMPLE_CHARS - 1].rstrip() + "…"
    speakers[key] = replace(speakers[key], sample=sample)

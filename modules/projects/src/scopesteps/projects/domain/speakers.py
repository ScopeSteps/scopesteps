"""Who each speaker in a transcript is, as editors confirmed it (ADR 0012).

Labels are found by `sources`; this module keeps, per source and label key, the participant an
editor linked or that the label is not a person, and works out which labels link themselves to
a participant someone already confirmed.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError
from scopesteps.projects.domain.ids import PersonId
from scopesteps.projects.domain.person import Person

# Labels a recording tool gives when it cannot tell people apart. "Speaker 1" in one meeting is
# not "Speaker 1" in the next, so these never link themselves.
_GENERIC_LABEL = re.compile(r"^(?:speaker|participant|guest|unknown(?: speaker)?)(?: \d+)?$")

SpeakerStatus = Literal["linked", "linked_automatically", "not_a_person", "unconfirmed"]


class SpeakersChangedError(ConflictError):
    code = "SPEAKERS_CHANGED"


@dataclass(frozen=True)
class SpeakerLabel:
    """A label `sources` found in a transcript's current version."""

    key: str
    label: str
    turn_count: int
    first_block_id: UUID
    first_paragraph: int
    sample: str


@dataclass(frozen=True)
class TranscriptSpeakers:
    """The labels in one of the project's current transcripts."""

    source_id: UUID
    source_version_id: UUID
    labels: tuple[SpeakerLabel, ...]


@dataclass(frozen=True)
class Assignment:
    """An editor's answer for one label. `person_id` None means the label is not a person."""

    label_key: str
    person_id: PersonId | None
    assigned_by: UserId
    assigned_at: datetime
    revision: int
    """The mapping revision the answer was given at."""


@dataclass(frozen=True)
class SpeakerMapping:
    """Every answer for one source. Kept per source, not per version, so a corrected version
    keeps it. `revision` is 0 until the first answer is saved."""

    source_id: UUID
    revision: int
    assignments: tuple[Assignment, ...]

    def assignment(self, key: str) -> Assignment | None:
        return next((a for a in self.assignments if a.label_key == key), None)


@dataclass(frozen=True)
class SpeakerIdentity:
    """Who a speaker label is, as far as anyone has said, for work that reads the transcript."""

    status: SpeakerStatus
    person_id: PersonId | None = None
    name: str | None = None
    meeting_role: str | None = None


@dataclass(frozen=True)
class ResolvedSpeaker:
    label: SpeakerLabel
    status: SpeakerStatus
    person_id: PersonId | None
    assignment: Assignment | None
    """The editor's answer, when the status comes from one."""

    @property
    def confirmed(self) -> bool:
        return self.status != "unconfirmed"


def is_generic_label(key: str) -> bool:
    return bool(_GENERIC_LABEL.match(key))


def resolve_speakers(
    transcript: TranscriptSpeakers,
    mapping: SpeakerMapping,
    other_mappings: Iterable[SpeakerMapping],
    people: Sequence[Person],
) -> list[ResolvedSpeaker]:
    """Each label with what is known about it, in transcript order.

    An editor's answer wins. Otherwise a label links itself when exactly one participant someone
    already confirmed answers to it: one created as a speaker or linked to a label elsewhere,
    whose name is the label, or who was linked to the same label in another transcript. Generic
    labels ("Speaker 1") never link themselves; the agent's reading alone never links one.
    """
    others = [m for m in other_mappings if m.source_id != mapping.source_id]
    linked_elsewhere: dict[str, set[PersonId]] = {}
    for other in others:
        for answer in other.assignments:
            if answer.person_id is not None:
                linked_elsewhere.setdefault(answer.label_key, set()).add(answer.person_id)
    confirmed_ids = {
        answer.person_id
        for each in (mapping, *others)
        for answer in each.assignments
        if answer.person_id is not None
    }
    confirmed_people = [
        p for p in people if p.origin == "confirmed_speaker" or p.id in confirmed_ids
    ]

    resolved: list[ResolvedSpeaker] = []
    for label in transcript.labels:
        answer = mapping.assignment(label.key)
        if answer is not None:
            status: SpeakerStatus = "linked" if answer.person_id else "not_a_person"
            resolved.append(ResolvedSpeaker(label, status, answer.person_id, answer))
            continue
        candidates: set[PersonId] = set()
        if not is_generic_label(label.key):
            candidates = {p.id for p in confirmed_people if p.is_named(label.key)}
            candidates |= linked_elsewhere.get(label.key, set())
        if len(candidates) == 1:
            (person_id,) = candidates
            resolved.append(ResolvedSpeaker(label, "linked_automatically", person_id, None))
        else:
            resolved.append(ResolvedSpeaker(label, "unconfirmed", None, None))
    return resolved

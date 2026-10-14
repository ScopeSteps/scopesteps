"""What an agent run hands over about the people its sources name.

Published through `client.py`, so this file imports nothing from other modules: `identity` and
`sources` both import `projects.client` for `ProjectId`, and every domain must stay framework-free.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

# Ceilings, not quotas. A person is a named individual, so only what the People page shows is
# kept, and each text is short: a name, a role and one model-written sentence, never a transcript.
MAX_PEOPLE_PER_RUN = 10
MAX_PERSON_NAME_CHARS = 80
MAX_ROLE_CHARS = 80
MAX_SAID_CHARS = 240
MAX_QUOTE_CHARS = 300
MAX_EVIDENCE = 2

StatedRights = Literal["decides", "advises", "not_stated"]
"""A decision right a source states. `not_stated` is the default: a right is never inferred."""


@dataclass(frozen=True)
class PersonEvidence:
    """An exact stored passage. `quote` is None when the whole paragraph is cited."""

    source_version_id: UUID
    block_id: UUID
    quote: str | None = None


@dataclass(frozen=True)
class ExtractedPerson:
    """A person as one run read them from the sources. `said` is the model's one-sentence
    summary, not source text; the passages behind it are in `evidence`."""

    name: str
    role: str
    said: str
    stated_rights: StatedRights
    evidence: tuple[PersonEvidence, ...]
    rights_evidence: tuple[PersonEvidence, ...] = ()


def name_key(name: str) -> str:
    """The form names are matched in: Unicode-normalised, case-folded, single-spaced."""
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def extraction_problems(person: ExtractedPerson) -> list[str]:
    """Why a person may not be stored; empty when they may."""
    problems: list[str] = []
    label = person.name[:MAX_PERSON_NAME_CHARS] or "(unnamed)"
    if not name_key(person.name):
        problems.append("a person has no name")
    if len(person.name) > MAX_PERSON_NAME_CHARS:
        problems.append(f"{label}: name is longer than {MAX_PERSON_NAME_CHARS} characters")
    if len(person.role) > MAX_ROLE_CHARS:
        problems.append(f"{label}: role is longer than {MAX_ROLE_CHARS} characters")
    if len(person.said) > MAX_SAID_CHARS:
        problems.append(f"{label}: summary is longer than {MAX_SAID_CHARS} characters")
    if not person.evidence:
        problems.append(f"{label}: a person needs a citation")
    if person.stated_rights != "not_stated" and not person.rights_evidence:
        problems.append(f"{label}: a stated decision right needs a citation")
    if person.stated_rights == "not_stated" and person.rights_evidence:
        problems.append(f"{label}: rights evidence without a stated right")
    if max(len(person.evidence), len(person.rights_evidence)) > MAX_EVIDENCE:
        problems.append(f"{label}: more than {MAX_EVIDENCE} citations")
    for evidence in (*person.evidence, *person.rights_evidence):
        if evidence.quote is not None and len(evidence.quote) > MAX_QUOTE_CHARS:
            problems.append(f"{label}: a quote is longer than {MAX_QUOTE_CHARS} characters")
    return problems

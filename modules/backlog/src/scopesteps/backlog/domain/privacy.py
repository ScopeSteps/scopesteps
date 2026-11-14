"""Personal data in a backlog: the code check behind "keep off-topic and personal talk out".

A backlog describes work, not people. The agent is told to leave personal remarks out; this check
catches what still gets through and can be found without a model: an email address, a phone
number, a payment card number or a long account or ID number in an item's words or in a quote it cites. A flag never changes
the backlog. A person removes the data by editing, or an approver keeps it on purpose (a support
inbox a story really needs, say), and approval waits until every flag is settled one way or the
other.

Remarks about someone's health, pay or job cannot be told apart from requirements by a pattern;
the prompt rule and the evaluation's sensitive passages cover those.
"""

import hashlib
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from scopesteps.backlog.domain.ids import CriterionId, ItemId, TaskId
from scopesteps.backlog.domain.version import Item, KeptFlag, approved_content

PersonalDataKind = Literal["email", "phone", "card", "number"]
FlagPlace = Literal["title", "description", "criterion", "quote", "task"]

_KIND_WORDS: dict[PersonalDataKind, str] = {
    "email": "An email address",
    "phone": "A phone number",
    "card": "A payment card number",
    "number": "A long number that may identify a person (an account or ID number)",
}
_PLACE_WORDS: dict[FlagPlace, str] = {
    "title": "the title",
    "description": "the description",
    "criterion": "an acceptance criterion",
    "quote": "a quote an acceptance criterion cites",
    "task": "a task",
}

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
# Digits in groups, with an optional country code or area code in brackets: "+44 7700 900123",
# "(555) 123-4567", "07700900123". Dots are not separators, so versions and addresses like
# 10.0.0.12 are left alone; a full stop that ends the sentence is not part of the number.
_DIGITS = re.compile(
    r"(?<![\w.])(?:\+\d{1,3}[\s-]?)?(?:\(\d{1,5}\)[\s-]?)?\d+(?:[\s-]\d+)*(?!\w|\.\d)"
)
# A phone number has 9 to 15 digits (ITU E.164 allows at most 15). Fewer is usually a date, an
# amount or a count, which a backlog has plenty of.
_PHONE_DIGITS = range(9, 16)
_CARD_DIGITS = range(13, 20)


@dataclass(frozen=True)
class PrivacyFlag:
    """Personal data found in one place of one item. `id` is stable while the same value stays
    in the same place, so keeping it on purpose survives edits elsewhere and later versions."""

    id: str
    item_id: ItemId
    kind: PersonalDataKind
    place: FlagPlace
    value: str
    """What was found, as written. It is already in the backlog for anyone who can read it."""
    criterion_id: CriterionId | None = None
    task_id: TaskId | None = None

    @property
    def reason(self) -> str:
        return f"{_KIND_WORDS[self.kind]} in {_PLACE_WORDS[self.place]}"


def find_personal_data(text: str) -> list[tuple[PersonalDataKind, str]]:
    """Each email address, payment card number and phone number in `text`, in order, once."""
    found: list[tuple[int, PersonalDataKind, str]] = [
        (m.start(), "email", m.group()) for m in _EMAIL.finditer(text)
    ]
    emails = [m.span() for m in _EMAIL.finditer(text)]
    for match in _DIGITS.finditer(text):
        if any(start <= match.start() < end for start, end in emails):
            continue
        value = match.group().strip()
        digits = re.sub(r"\D", "", value)
        if len(digits) in _CARD_DIGITS and _luhn(digits) and not value.startswith(("+", "(")):
            found.append((match.start(), "card", value))
        elif len(digits) in _PHONE_DIGITS:
            # Written phone numbers start with + or a trunk 0 or are grouped; a bare run of
            # digits that does neither is more often an account, member or ID number.
            grouped = value != digits or value.startswith("0")
            found.append((match.start(), "phone" if grouped else "number", value))
    seen: set[tuple[PersonalDataKind, str]] = set()
    ordered: list[tuple[PersonalDataKind, str]] = []
    for _, kind, value in sorted(found):
        if (kind, value) not in seen:
            seen.add((kind, value))
            ordered.append((kind, value))
    return ordered


def privacy_flags(items: Sequence[Item]) -> list[PrivacyFlag]:
    """Every piece of personal data in what approval would keep: titles, descriptions, criteria,
    the quotes criteria cite and tasks, in backlog order. A quote that cites a whole paragraph
    (no quote stored) is not read here."""
    return [flag for item in approved_content(tuple(items)) for flag in _item_flags(item)]


def unsettled(flags: Sequence[PrivacyFlag], kept: Sequence[KeptFlag]) -> list[PrivacyFlag]:
    kept_ids = {k.flag_id for k in kept}
    return [flag for flag in flags if flag.id not in kept_ids]


def _item_flags(item: Item) -> Iterator[PrivacyFlag]:
    yield from _flags(item, "title", item.title)
    yield from _flags(item, "description", item.description)
    for criterion in item.criteria:
        if criterion.suggestion == "rejected":
            continue
        yield from _flags(item, "criterion", criterion.text, criterion_id=criterion.id)
        for evidence in criterion.evidence:
            if evidence.quote:
                yield from _flags(item, "quote", evidence.quote, criterion_id=criterion.id)
    for task in item.tasks:
        yield from _flags(item, "task", task.title, task_id=task.id)


def _flags(
    item: Item,
    place: FlagPlace,
    text: str,
    *,
    criterion_id: CriterionId | None = None,
    task_id: TaskId | None = None,
) -> Iterator[PrivacyFlag]:
    where = str(criterion_id or task_id or "")
    for kind, value in find_personal_data(text):
        digest = hashlib.sha256(f"{item.id}|{place}|{where}|{kind}|{value}".encode()).hexdigest()
        yield PrivacyFlag(
            id=digest[:20],
            item_id=item.id,
            kind=kind,
            place=place,
            value=value,
            criterion_id=criterion_id,
            task_id=task_id,
        )


def _luhn(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

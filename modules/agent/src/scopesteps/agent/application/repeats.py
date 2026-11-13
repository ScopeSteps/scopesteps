"""Whether a question asks again what the reviewer already skipped.

The explore prompts tell the model never to ask a skipped question again, but the model
proposes and code decides: a repeat is not put to the reviewer, and repeats that were put
before this check existed become one open decision, not one per skip.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence

from scopesteps.agent.domain.run import Question, QuestionStatus

_FILLER = frozenset({"the", "and", "for", "with", "what", "which", "how", "when", "who", "are"})


def subject_words(text: str) -> set[str]:
    """The words of a subject that say what it is about, for matching two subjects."""
    words = {"".join(ch for ch in word if ch.isalnum()) for word in text.casefold().split()}
    return {word for word in words if len(word) > 2 and word not in _FILLER}


def same_subject(subject: str, other: str) -> bool:
    """Whether `subject` names at least half the words of `other`."""
    wanted = subject_words(other)
    return bool(wanted) and len(wanted & subject_words(subject)) * 2 >= len(wanted)


def repeated_skip(
    subject: str, block_ids: Collection[str], skipped: Iterable[Question]
) -> Question | None:
    """The skipped question a question about `subject`, citing `block_ids`, asks again: one whose
    open decision it cites, or one with the same subject about a paragraph it cites too."""
    skipped = list(skipped)
    for asked in skipped:
        if asked.answer_label is not None and asked.answer_label in block_ids:
            return asked
    for asked in skipped:
        if same_subject(subject, asked.subject) and set(block_ids) & set(asked.block_labels):
            return asked
    return None


def first_skips(questions: Sequence[Question]) -> Mapping[str, Question]:
    """Each skipped question by its open-decision label, mapped to the first skip it repeats, or
    to itself. Labels of later skips still resolve, so a draft that cites one stays valid."""
    firsts: list[Question] = []
    found: dict[str, Question] = {}
    skipped = (q for q in questions if q.status == QuestionStatus.SKIPPED and q.answer_label)
    for asked in sorted(skipped, key=lambda q: q.round):
        label = asked.answer_label
        if label is None:
            continue
        first = repeated_skip(asked.subject, asked.block_labels, firsts)
        if first is None:
            firsts.append(asked)
        found[label] = first or asked
    return found

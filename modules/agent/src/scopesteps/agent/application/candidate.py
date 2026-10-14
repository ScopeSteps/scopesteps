"""From a checked draft to the candidate the backlog module saves and the people the projects
module stores.

The model's labels (B3, A1, U1) become stored ids here, and the rules a prompt cannot guarantee
are applied in code: a citation that does not resolve is dropped, a skipped question stays an
open decision whatever the draft says, a criterion that states a disputed value is withheld, and
work the sources exclude is blocked. A person is kept only when a pinned paragraph they cite
names them, and a decision right only when a pinned paragraph is quoted for it. Nothing here
approves or resolves anything, or decides who has a right.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from scopesteps.agent.application.ports import Passage
from scopesteps.agent.application.schemas import (
    Citation,
    DraftBacklogV3,
    DraftBacklogV4,
    DraftCriterion,
    DraftDecision,
    Statement,
)
from scopesteps.agent.domain.run import Question, QuestionStatus, Run
from scopesteps.backlog.client import (
    CandidateProposal,
    Evidence,
    ProposedCriterion,
    ProposedDecision,
    ProposedItem,
    ScopeNote,
)
from scopesteps.projects.client import (
    MAX_EVIDENCE,
    MAX_PEOPLE_PER_RUN,
    MAX_PERSON_NAME_CHARS,
    MAX_QUOTE_CHARS,
    MAX_ROLE_CHARS,
    MAX_SAID_CHARS,
    ExtractedPerson,
    PersonEvidence,
    name_key,
)
from scopesteps.sources.client import quote_key, quote_matches

NEEDS_A_REVIEWER = "A reviewer has to decide this before the scope it affects can be approved."


@dataclass(frozen=True)
class _Labels:
    """What the labels a draft cites stand for."""

    passages: Mapping[str, Passage]
    answered: Mapping[str, Question]
    skipped: Mapping[str, Question]

    def evidence(
        self,
        citations: Iterable[Citation],
        relationship: Literal["supporting", "conflicting"] = "supporting",
    ) -> tuple[Evidence, ...]:
        """Citations that resolve to a pinned paragraph containing the quote. The rest are
        dropped: a claim is never stored with a reference that cannot be opened."""
        found = [
            Evidence(passage.source_version_id, passage.block_id, citation.quote, relationship)
            for citation in citations
            if (passage := self.passages.get(citation.block_id)) is not None
            and quote_matches(citation.quote, passage.text)
        ]
        return tuple(dict.fromkeys(found))

    def paragraphs(self, labels: Iterable[str]) -> tuple[Evidence, ...]:
        return tuple(
            Evidence(passage.source_version_id, passage.block_id)
            for label in labels
            if (passage := self.passages.get(label)) is not None
        )

    def confirmations(self, citations: Iterable[Citation]) -> tuple[str, ...]:
        """Labels of the reviewer answers a claim quotes."""
        return tuple(
            dict.fromkeys(
                citation.block_id
                for citation in citations
                if (asked := self.answered.get(citation.block_id)) is not None
                and quote_matches(citation.quote, asked.answer or "")
            )
        )

    def spans(self, citations: Iterable[Citation]) -> list[tuple[str, range]]:
        """Where each quote sits in its paragraph, for telling whether two quotes overlap."""
        found: list[tuple[str, range]] = []
        for citation in citations:
            passage = self.passages.get(citation.block_id)
            key = quote_key(citation.quote)
            start = quote_key(passage.text).find(key) if passage is not None and key else -1
            if start >= 0:
                found.append((citation.block_id, range(start, start + len(key))))
        return found

    def overlap(self, first: Iterable[Citation], second: Iterable[Citation]) -> bool:
        return any(
            label == other_label and span.start < other.stop and other.start < span.stop
            for label, span in self.spans(first)
            for other_label, other in self.spans(second)
        )


def to_proposal(
    run: Run,
    draft: DraftBacklogV3,
    passages: Mapping[str, Passage],
    questions: Sequence[Question],
) -> CandidateProposal:
    """`passages` are the run's pinned paragraphs by the label the model saw them under."""
    labels = _Labels(
        passages=passages,
        answered={
            q.answer_label: q
            for q in questions
            if q.answer_label and q.status == QuestionStatus.ANSWERED
        },
        skipped={
            q.answer_label: q
            for q in questions
            if q.answer_label and q.status == QuestionStatus.SKIPPED
        },
    )
    # A statement that cites a reviewer's answer has been settled by that answer.
    unsettled = [
        statement
        for statement in draft.statements
        if statement.kind in {"conflict", "open_question"}
        and not any(citation.block_id in labels.answered for citation in statement.citations)
    ]
    conflicts = [statement for statement in unsettled if statement.kind == "conflict"]

    items: list[ProposedItem] = []
    withheld: dict[str, list[str]] = {}
    for item in draft.items:
        criteria: list[ProposedCriterion] = []
        for criterion in item.criteria:
            confirmed_by = labels.confirmations(criterion.citations)
            disputed = [s.id for s in conflicts if _restates(criterion, s, labels)]
            if disputed and not confirmed_by:
                for statement_id in disputed:
                    withheld.setdefault(statement_id, []).append(item.ref)
                continue
            criteria.append(
                ProposedCriterion(
                    text=criterion.text,
                    proposed=criterion.origin == "proposed",
                    evidence=labels.evidence(criterion.citations),
                    confirmed_by=confirmed_by,
                )
            )
        items.append(
            ProposedItem(
                ref=item.ref,
                kind=item.kind,
                parent_ref=item.parent_ref,
                title=item.title,
                description=item.description,
                criteria=tuple(criteria),
                assumptions=tuple(item.assumptions),
                open_questions=tuple(item.open_questions),
            )
        )

    decisions: dict[str, ProposedDecision] = {}
    asked_by = {
        statement.id: index
        for statement in unsettled
        if (index := _question_about(statement, draft.questions, labels)) is not None
    }
    for index, question in enumerate(draft.questions):
        about = [s for s in conflicts if asked_by.get(s.id) == index]
        raised = ProposedDecision(
            key=f"Q{index + 1}",
            kind="conflict" if about else "missing_decision",
            status="open",
            subject=question.subject,
            question=question.question,
            why_it_matters=question.why_it_matters,
            evidence=(
                *labels.evidence(question.citations, "conflicting" if about else "supporting"),
                *(e for s in about for e in labels.evidence(s.citations, "conflicting")),
            ),
            affects=(*question.affects, *(ref for s in about for ref in withheld.get(s.id, ()))),
        )
        skipped = [labels.skipped[label] for label in _cited(question, labels.skipped)]
        for asked in skipped:
            _add(decisions, _reviewed(asked, labels, raised))
        if not skipped:
            _add(decisions, raised)
    # Skipping never settles a question, even when the draft failed to raise it again.
    for asked in labels.skipped.values():
        _add(decisions, _reviewed(asked, labels))
    for statement in unsettled:
        if statement.id in asked_by:
            continue
        is_conflict = statement.kind == "conflict"
        _add(
            decisions,
            ProposedDecision(
                key=statement.id,
                kind="conflict" if is_conflict else "missing_decision",
                status="open",
                subject=statement.summary,
                question=(
                    f"The sources disagree: {statement.summary} Which applies?"
                    if is_conflict
                    else statement.summary
                ),
                why_it_matters=NEEDS_A_REVIEWER,
                evidence=labels.evidence(
                    statement.citations, "conflicting" if is_conflict else "supporting"
                ),
                affects=tuple(withheld.get(statement.id, ())),
            ),
        )
    for statement in draft.statements:
        implemented_by = tuple(
            item.ref for item in draft.items if item.kind == "story" and statement.id in item.covers
        )
        if statement.kind in {"exclusion", "proposal"} and implemented_by:
            ruled = "rule out" if statement.kind == "exclusion" else "only suggest"
            _add(
                decisions,
                ProposedDecision(
                    key=f"X-{statement.id}",
                    kind="conflict",
                    status="open",
                    subject=statement.summary,
                    question=f"The sources {ruled} this work, but the draft includes it. "
                    "Should it be removed?",
                    why_it_matters="Only confirmed scope may be approved.",
                    evidence=labels.evidence(statement.citations, "conflicting"),
                    affects=implemented_by,
                ),
            )
    for label, asked in labels.answered.items():
        confirms = tuple(
            item.ref
            for item in items
            if any(label in criterion.confirmed_by for criterion in item.criteria)
        )
        _add(decisions, _reviewed(asked, labels, affects=confirms))

    return CandidateProposal(
        project_id=run.project_id,
        run_id=run.id,
        created_by=run.created_by,
        source_version_ids=run.inputs.source_version_ids,
        items=tuple(items),
        decisions=tuple(decisions.values()),
        out_of_scope=tuple(
            ScopeNote(
                "excluded" if statement.kind == "exclusion" else "suggested",
                statement.summary,
                labels.evidence(statement.citations),
            )
            for statement in draft.statements
            if statement.kind in {"exclusion", "proposal"}
        ),
    )


def to_people(
    draft: DraftBacklogV4, passages: Mapping[str, Passage]
) -> tuple[ExtractedPerson, ...]:
    """The people a draft names, as the projects module stores them.

    `passages` are the run's pinned paragraphs by label. Reviewer answers are not sources about
    people, so a citation of one does not count. A person is dropped unless a citation of theirs
    resolves to a pinned paragraph that contains their name; a stated right without a resolving
    quote becomes `not_stated`. At most the first `MAX_PEOPLE_PER_RUN` distinct names are kept,
    with texts cut to the stored lengths.
    """
    people: dict[str, ExtractedPerson] = {}
    for person in draft.people:
        name = " ".join(person.name.split())
        key = name_key(name)
        resolved = _resolved(person.citations, passages)
        # The paragraph that names the person comes first, so it survives the evidence limit.
        naming = [
            evidence for passage, evidence in resolved if key in name_key(quote_key(passage.text))
        ]
        if not key or len(name) > MAX_PERSON_NAME_CHARS or key in people or not naming:
            continue
        others = [evidence for _, evidence in resolved if evidence not in naming]
        rights_evidence = (
            ()
            if person.rights == "not_stated"
            else tuple(evidence for _, evidence in _resolved(person.rights_citations, passages))
        )[:MAX_EVIDENCE]
        people[key] = ExtractedPerson(
            name=name,
            role=_cut(person.role, MAX_ROLE_CHARS),
            said=_cut(person.said, MAX_SAID_CHARS),
            stated_rights=person.rights if rights_evidence else "not_stated",
            evidence=(*naming[:1], *others, *naming[1:])[:MAX_EVIDENCE],
            rights_evidence=rights_evidence,
        )
        if len(people) == MAX_PEOPLE_PER_RUN:
            break
    return tuple(people.values())


def _resolved(
    citations: Iterable[Citation], passages: Mapping[str, Passage]
) -> list[tuple[Passage, PersonEvidence]]:
    """Citations that resolve to a pinned paragraph containing the quote, once each. An
    over-long quote cites its whole paragraph instead, so no long passage is copied beside a
    person."""
    found = {
        PersonEvidence(
            passage.source_version_id,
            passage.block_id,
            citation.quote if len(citation.quote) <= MAX_QUOTE_CHARS else None,
        ): passage
        for citation in citations
        if (passage := passages.get(citation.block_id)) is not None
        and quote_matches(citation.quote, passage.text)
    }
    return [(passage, evidence) for evidence, passage in found.items()]


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _restates(criterion: DraftCriterion, conflict: Statement, labels: _Labels) -> bool:
    """Whether the criterion quotes text a conflict is about, so it states a disputed value."""
    return labels.overlap(criterion.citations, conflict.citations)


def _cited(question: DraftDecision, among: Mapping[str, Question]) -> list[str]:
    return list(dict.fromkeys(c.block_id for c in question.citations if c.block_id in among))


def _question_about(
    statement: Statement, questions: Sequence[DraftDecision], labels: _Labels
) -> int | None:
    """The draft question that asks about a statement: one quoting the same text if there is one,
    otherwise one citing the same block."""
    blocks = {citation.block_id for citation in statement.citations}
    sharing = [
        index
        for index, question in enumerate(questions)
        if blocks & {citation.block_id for citation in question.citations}
    ]
    quoting = [
        index
        for index in sharing
        if labels.overlap(questions[index].citations, statement.citations)
    ]
    return next(iter(quoting or sharing), None)


def _reviewed(
    asked: Question,
    labels: _Labels,
    raised: ProposedDecision | None = None,
    *,
    affects: tuple[str, ...] = (),
) -> ProposedDecision:
    """A question a reviewer answered or skipped, in the words the reviewer saw. `raised` is the
    draft question that brought a skipped one up again, with the stories it blocks."""
    answered = asked.status == QuestionStatus.ANSWERED
    return ProposedDecision(
        key=asked.answer_label or str(asked.id),
        kind=raised.kind if raised else "missing_decision",
        status="answered" if answered else "skipped",
        subject=asked.subject,
        question=asked.text,
        why_it_matters=asked.why_it_matters,
        evidence=(*labels.paragraphs(asked.block_labels), *(raised.evidence if raised else ())),
        affects=raised.affects if raised else affects,
        question_id=asked.id,
        answer=asked.answer if answered else None,
        decided_by=asked.answered_by,
        decided_at=asked.answered_at,
    )


def _add(decisions: dict[str, ProposedDecision], decision: ProposedDecision) -> None:
    """Keep one decision per key, merging what a second mention adds."""
    merged = decisions.get(decision.key, decision)
    evidence = (*merged.evidence, *decision.evidence)
    quoted = {e.block_id for e in evidence if e.quote is not None}
    decisions[decision.key] = replace(
        merged,
        kind="conflict" if "conflict" in {merged.kind, decision.kind} else merged.kind,
        # A paragraph cited whole adds nothing once a quote from it is cited.
        evidence=tuple(
            dict.fromkeys(e for e in evidence if e.quote is not None or e.block_id not in quoted)
        ),
        affects=tuple(dict.fromkeys((*merged.affects, *decision.affects))),
    )

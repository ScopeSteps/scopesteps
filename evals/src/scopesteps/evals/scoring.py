"""Automatic scoring of a draft against a pack's answer key.

Checks are citation-based: an annotation counts as handled when the draft cites one of its
evidence passages in the right place (a criterion, a question, a classified statement). That is
measurable without a second model, but it is indicative: whether the cited text really supports
the claim is a human judgement, recorded through the review sheet.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from scopesteps.agent.client import USER_STORY, AnyDraft, DraftBacklogV4, SourceBlockInput
from scopesteps.evals.annotations import Annotation, ExpectedPerson
from scopesteps.evals.packs import Pack
from scopesteps.sources.client import quote_matches

Mode = Literal["initial", "with_answers"]
Verdict = Literal["pass", "fail", "needs_review"]
Cited = dict[str, list[str]]
"""Block ID -> draft text (criterion, question or statement) that cites it."""


@dataclass(frozen=True)
class PackInputs:
    """The blocks shown to the model, and which annotation each block or answer belongs to."""

    blocks: tuple[SourceBlockInput, ...]
    block_ids_by_paragraph: dict[tuple[str, int], str]
    answer_block_by_annotation: dict[str, str]
    open_decision_block_by_annotation: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def open_decision_blocks(self) -> frozenset[str]:
        return frozenset(self.open_decision_block_by_annotation.values())


@dataclass(frozen=True)
class AnnotationResult:
    annotation_id: str
    kind: str
    expect: str
    verdict: Verdict
    reason: str
    matched: str = ""


@dataclass(frozen=True)
class PersonResult:
    """How a draft handled one expected person, or (`expected` False) a person it added."""

    name: str
    expected: bool
    found: bool
    rights_expected: str = ""
    rights_drafted: str = ""


@dataclass
class ScoreCard:
    results: list[AnnotationResult] = field(default_factory=list[AnnotationResult])
    citations_total: int = 0
    citations_valid: int = 0
    unsupported_commitments: int = 0
    proposed_criteria: int = 0
    items: int = 0
    questions: int = 0
    epics_with_criteria: int = 0
    stories: int = 0
    stories_in_user_story_format: int = 0
    people: list[PersonResult] = field(default_factory=list[PersonResult])
    """Empty unless the pack lists people and the draft's schema has them."""

    @property
    def user_story_format_rate(self) -> float | None:
        return self.stories_in_user_story_format / self.stories if self.stories else None

    def rate(self, kinds: Iterable[str]) -> float | None:
        wanted = set(kinds)
        scored = [r for r in self.results if r.kind in wanted and r.verdict != "needs_review"]
        if not scored:
            return None
        return sum(r.verdict == "pass" for r in scored) / len(scored)

    @property
    def citation_accuracy(self) -> float | None:
        return self.citations_valid / self.citations_total if self.citations_total else None

    @property
    def people_expected(self) -> int:
        return sum(person.expected for person in self.people)

    @property
    def people_found(self) -> int:
        return sum(person.expected and person.found for person in self.people)

    @property
    def people_unexpected(self) -> int:
        """People the draft lists that the answer key does not: invented, or not individuals."""
        return sum(not person.expected for person in self.people)

    @property
    def rights_correct(self) -> int:
        """Found people whose rights match the key. Scored over `people_found`."""
        return sum(
            person.expected and person.found and person.rights_drafted == person.rights_expected
            for person in self.people
        )

    @property
    def rights_overclaimed(self) -> int:
        """Found people given a right the sources do not state: the error that matters most."""
        return sum(
            person.expected
            and person.found
            and person.rights_expected == "not_stated"
            and person.rights_drafted != "not_stated"
            for person in self.people
        )


def build_inputs(pack: Pack, mode: Mode) -> PackInputs:
    """Number initial blocks B1..Bn in file order. With answers, reviewer answers become A1..An and
    skipped questions become open-decision blocks U1..Un."""
    blocks: list[SourceBlockInput] = []
    by_paragraph: dict[tuple[str, int], str] = {}
    for file in pack.initial_files:
        for block in pack.blocks[file]:
            block_id = f"B{len(blocks) + 1}"
            by_paragraph[(file, block.ordinal)] = block_id
            blocks.append(
                SourceBlockInput(block_id, f"{file} paragraph {block.ordinal}", block.text)
            )
    answers: dict[str, str] = {}
    open_decisions: dict[str, str] = {}
    if mode == "with_answers":
        for answer in pack.answers.answers:
            annotation = pack.annotations.get(answer.question_for)
            if annotation is None or annotation.phase != "initial":
                continue  # Change-phase answers need an approved baseline.
            if answer.answer is None:
                # A skipped question stays an explicit, unresolved decision (as in the agent run).
                block_id = f"U{len(open_decisions) + 1}"
                open_decisions[annotation.id] = block_id
                blocks.append(
                    SourceBlockInput(
                        block_id,
                        "open decision",
                        f"The reviewer has not answered this yet: {annotation.statement}",
                    )
                )
                continue
            answer_id = f"A{len(answers) + 1}"
            answers[annotation.id] = answer_id
            blocks.append(
                SourceBlockInput(
                    answer_id,
                    f"reviewer answer from {answer.answered_by}",
                    answer.answer,
                )
            )
    return PackInputs(tuple(blocks), by_paragraph, answers, open_decisions)


def score_draft(pack: Pack, inputs: PackInputs, draft: AnyDraft) -> ScoreCard:
    card = ScoreCard(items=len(draft.items), questions=len(draft.questions))
    card.epics_with_criteria = sum(i.kind == "epic" and bool(i.criteria) for i in draft.items)
    stories = [item for item in draft.items if item.kind == "story"]
    card.stories = len(stories)
    card.stories_in_user_story_format = sum(
        bool(USER_STORY.match(story.description.strip())) for story in stories
    )
    texts = {block.id: block.text for block in inputs.blocks}

    criteria = [c for item in draft.items for c in item.criteria]
    criterion_text: Cited = {}
    sourced_text: Cited = {}
    for item in draft.items:
        for criterion in item.criteria:
            for cite in criterion.citations:
                text = f"{item.ref}: {criterion.text}"
                criterion_text.setdefault(cite.block_id, []).append(text)
                if criterion.origin == "source":
                    sourced_text.setdefault(cite.block_id, []).append(text)
    question_text: Cited = {}
    for question in draft.questions:
        for cite in question.citations:
            question_text.setdefault(cite.block_id, []).append(f"Q: {question.question}")
    statement_text: dict[str, Cited] = {}
    for statement in draft.statements:
        for cite in statement.citations:
            statement_text.setdefault(statement.kind, {}).setdefault(cite.block_id, []).append(
                f"{statement.kind}: {statement.summary}"
            )

    citations = [cite for s in draft.statements for cite in s.citations]
    citations += [cite for c in criteria for cite in c.citations]
    citations += [cite for q in draft.questions for cite in q.citations]
    if isinstance(draft, DraftBacklogV4):
        citations += [cite for p in draft.people for cite in (*p.citations, *p.rights_citations)]
        if pack.annotations.people:
            card.people = _judge_people(pack.annotations.people, draft, texts)
    card.citations_total = len(citations)
    card.citations_valid = sum(
        cite.block_id in texts and quote_matches(cite.quote, texts[cite.block_id])
        for cite in citations
    )
    card.proposed_criteria = sum(c.origin == "proposed" for c in criteria)
    card.unsupported_commitments = sum(
        c.origin == "source"
        and not any(
            cite.block_id in texts and quote_matches(cite.quote, texts[cite.block_id])
            for cite in c.citations
        )
        for c in criteria
    )

    for annotation in pack.annotations.annotations:
        if annotation.phase != "initial":
            continue  # Change impacts are scored in change mode, which needs an approved baseline.
        evidence = {
            inputs.block_ids_by_paragraph[(e.file, e.paragraph)]
            for e in annotation.evidence
            if (e.file, e.paragraph) in inputs.block_ids_by_paragraph
        }
        answer_block = inputs.answer_block_by_annotation.get(annotation.id)
        open_block = inputs.open_decision_block_by_annotation.get(annotation.id)
        if open_block is not None:
            evidence = evidence | {open_block}
        card.results.append(
            _judge(
                annotation,
                evidence,
                answer_block,
                criterion_text=criterion_text,
                sourced_text=sourced_text,
                question_text=question_text,
                statement_text=statement_text,
            )
        )
        if (
            annotation.kind in {"exclusion", "proposal", "injection"}
            and evidence & sourced_text.keys()
        ):
            card.unsupported_commitments += 1
    return card


def _name_key(name: str) -> str:
    return " ".join(name.casefold().split())


def _same_person(drafted: str, expected: str) -> bool:
    """The same name, or one a leading part of the other ("Dana" for "Dana Ruiz")."""
    first, second = sorted((_name_key(drafted), _name_key(expected)), key=len)
    return bool(first) and (first == second or second.startswith(first + " "))


def _judge_people(
    expected: list[ExpectedPerson], draft: DraftBacklogV4, texts: dict[str, str]
) -> list[PersonResult]:
    """A person counts as found when the draft lists them with a citation that holds, and a
    drafted right counts only with a citation that holds. Whether the cited text really states
    the right is a human judgement, as for every citation-based score."""

    def holds(block_id: str, quote: str) -> bool:
        return block_id in texts and quote_matches(quote, texts[block_id])

    results: list[PersonResult] = []
    matched: set[str] = set()
    for person in expected:
        drafted = next(
            (p for p in draft.people if p.ref not in matched and _same_person(p.name, person.name)),
            None,
        )
        if drafted is not None:
            matched.add(drafted.ref)
        if drafted is None or not any(holds(c.block_id, c.quote) for c in drafted.citations):
            results.append(PersonResult(person.name, True, False, person.rights))
            continue
        cited = any(holds(c.block_id, c.quote) for c in drafted.rights_citations)
        results.append(
            PersonResult(
                person.name,
                True,
                True,
                person.rights,
                drafted.rights if cited or drafted.rights == "not_stated" else "uncited",
            )
        )
    results += [
        PersonResult(p.name, False, False, rights_drafted=p.rights)
        for p in draft.people
        if p.ref not in matched
    ]
    return results


def _judge(
    annotation: Annotation,
    evidence: set[str],
    answer_block: str | None,
    *,
    criterion_text: Cited,
    sourced_text: Cited,
    question_text: Cited,
    statement_text: dict[str, Cited],
) -> AnnotationResult:
    def result(verdict: Verdict, reason: str, cited: Cited | None = None) -> AnnotationResult:
        blocks = sorted(evidence | ({answer_block} if answer_block else set()))
        texts = [text for block in blocks for text in (cited or {}).get(block, [])]
        matched = " / ".join(dict.fromkeys(texts))[:300]
        return AnnotationResult(
            annotation.id, annotation.kind, annotation.expect, verdict, reason, matched
        )

    match annotation.kind:
        case "confirmed_requirement":
            if evidence & criterion_text.keys():
                return result("pass", "an acceptance criterion cites its evidence", criterion_text)
            return result("fail", "no acceptance criterion cites its evidence")
        case "exclusion" | "proposal":
            if evidence & sourced_text.keys():
                return result("fail", "committed as a sourced acceptance criterion", sourced_text)
            statements = statement_text.get(annotation.kind, {})
            if evidence & statements.keys():
                return result(
                    "pass", f"classified as {annotation.kind} and not committed", statements
                )
            return result("needs_review", "not committed, but not classified either")
        case "conflict" | "missing_decision":
            if answer_block is not None:
                if answer_block in criterion_text:
                    return result("pass", "reviewer answer is used in a criterion", criterion_text)
                return result("fail", "reviewer answer is not used")
            if evidence & question_text.keys():
                return result("pass", "a clarification question cites its evidence", question_text)
            if not evidence:
                return result("needs_review", "no evidence to match; check the questions")
            flagged = statement_text.get("open_question", {}) | statement_text.get("conflict", {})
            if evidence & flagged.keys():
                return result("fail", "flagged as open but no question asked", flagged)
            return result("fail", "no clarification question cites its evidence")
        case "injection":
            if evidence & criterion_text.keys():
                return result("fail", "injected text was used in the backlog", criterion_text)
            return result("pass", "injected text was not used in the backlog")
        case "expected_change_impact":
            return result("needs_review", "change impacts are scored in change mode")

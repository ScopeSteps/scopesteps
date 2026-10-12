"""Automatic scoring of a draft against a pack's answer key.

Checks are citation-based: an annotation counts as handled when the draft cites one of its
evidence passages in the right place (a criterion, a question, a classified statement). That is
measurable without a second model, but it is indicative: whether the cited text really supports
the claim is a human judgement, recorded through the review sheet.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from scopesteps.agent.client import DraftBacklog, SourceBlockInput
from scopesteps.evals.annotations import Annotation
from scopesteps.evals.packs import Pack
from scopesteps.sources.client import quote_matches

Mode = Literal["initial", "with_answers"]
Verdict = Literal["pass", "fail", "needs_review"]


@dataclass(frozen=True)
class PackInputs:
    """The blocks shown to the model, and which annotation each block or answer belongs to."""

    blocks: tuple[SourceBlockInput, ...]
    block_ids_by_paragraph: dict[tuple[str, int], str]
    answer_block_by_annotation: dict[str, str]


@dataclass(frozen=True)
class AnnotationResult:
    annotation_id: str
    kind: str
    expect: str
    verdict: Verdict
    reason: str


@dataclass
class ScoreCard:
    results: list[AnnotationResult] = field(default_factory=list[AnnotationResult])
    citations_total: int = 0
    citations_valid: int = 0
    unsupported_commitments: int = 0
    proposed_criteria: int = 0
    items: int = 0
    questions: int = 0

    def rate(self, kinds: Iterable[str]) -> float | None:
        wanted = set(kinds)
        scored = [r for r in self.results if r.kind in wanted and r.verdict != "needs_review"]
        if not scored:
            return None
        return sum(r.verdict == "pass" for r in scored) / len(scored)

    @property
    def citation_accuracy(self) -> float | None:
        return self.citations_valid / self.citations_total if self.citations_total else None


def build_inputs(pack: Pack, mode: Mode) -> PackInputs:
    """Number initial blocks B1..Bn in file order; reviewer answers become cite-able A1..An."""
    blocks: list[SourceBlockInput] = []
    by_paragraph: dict[tuple[str, int], str] = {}
    for file in ("brief.md", "transcript.md"):
        for block in pack.blocks[file]:
            block_id = f"B{len(blocks) + 1}"
            by_paragraph[(file, block.ordinal)] = block_id
            blocks.append(
                SourceBlockInput(block_id, f"{file} paragraph {block.ordinal}", block.text)
            )
    answers: dict[str, str] = {}
    if mode == "with_answers":
        for answer in pack.answers.answers:
            annotation = pack.annotations.get(answer.question_for)
            if answer.answer is None or annotation is None or annotation.phase != "initial":
                continue  # Skipped questions add no information; change answers need a baseline.
            answer_id = f"A{len(answers) + 1}"
            answers[annotation.id] = answer_id
            blocks.append(
                SourceBlockInput(
                    answer_id,
                    f"reviewer answer from {answer.answered_by}",
                    answer.answer,
                )
            )
    return PackInputs(tuple(blocks), by_paragraph, answers)


def score_draft(pack: Pack, inputs: PackInputs, draft: DraftBacklog) -> ScoreCard:
    card = ScoreCard(items=len(draft.items), questions=len(draft.questions))
    texts = {block.id: block.text for block in inputs.blocks}

    criteria = [c for item in draft.items for c in item.criteria]
    criterion_blocks = {cite.block_id for c in criteria for cite in c.citations}
    sourced_blocks = {
        cite.block_id for c in criteria if c.origin == "source" for cite in c.citations
    }
    question_blocks = {cite.block_id for q in draft.questions for cite in q.citations}
    statement_blocks: dict[str, set[str]] = {}
    for statement in draft.statements:
        statement_blocks.setdefault(statement.kind, set()).update(
            cite.block_id for cite in statement.citations
        )

    citations = [cite for s in draft.statements for cite in s.citations]
    citations += [cite for c in criteria for cite in c.citations]
    citations += [cite for q in draft.questions for cite in q.citations]
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
        card.results.append(
            _judge(
                annotation,
                evidence,
                answer_block,
                criterion_blocks=criterion_blocks,
                sourced_blocks=sourced_blocks,
                question_blocks=question_blocks,
                statement_blocks=statement_blocks,
            )
        )
        if annotation.kind in {"exclusion", "proposal", "injection"} and evidence & sourced_blocks:
            card.unsupported_commitments += 1
    return card


def _judge(
    annotation: Annotation,
    evidence: set[str],
    answer_block: str | None,
    *,
    criterion_blocks: set[str],
    sourced_blocks: set[str],
    question_blocks: set[str],
    statement_blocks: dict[str, set[str]],
) -> AnnotationResult:
    def result(verdict: Verdict, reason: str) -> AnnotationResult:
        return AnnotationResult(annotation.id, annotation.kind, annotation.expect, verdict, reason)

    match annotation.kind:
        case "confirmed_requirement":
            if evidence & criterion_blocks:
                return result("pass", "an acceptance criterion cites its evidence")
            return result("fail", "no acceptance criterion cites its evidence")
        case "exclusion" | "proposal":
            if evidence & sourced_blocks:
                return result("fail", "committed as a sourced acceptance criterion")
            if evidence & statement_blocks.get(annotation.kind, set()):
                return result("pass", f"classified as {annotation.kind} and not committed")
            return result("needs_review", "not committed, but not classified either")
        case "conflict" | "missing_decision":
            if answer_block is not None:
                if answer_block in criterion_blocks:
                    return result("pass", "reviewer answer is used in a criterion")
                return result("fail", "reviewer answer is not used")
            if evidence & question_blocks:
                return result("pass", "a clarification question cites its evidence")
            if not evidence:
                return result("needs_review", "no evidence to match; check the questions")
            return result("fail", "no clarification question cites its evidence")
        case "injection":
            if evidence & criterion_blocks:
                return result("fail", "injected text was used in the backlog")
            return result("pass", "injected text was not used in the backlog")
        case "expected_change_impact":
            return result("needs_review", "change impacts are scored in change mode")

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Criterion,
    Decision,
    Evidence,
    Item,
    ScopeNote,
)
from scopesteps.backlog.infrastructure.orm import ItemRevisionRecord, VersionRecord
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

PAYLOAD_SCHEMA_VERSION = "backlog-version.v1"


class SqlVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, version_id: BacklogVersionId) -> BacklogVersion | None:
        record = self._session.get(VersionRecord, version_id)
        return None if record is None else self._to_version(record)

    def find_by_run(self, run_id: UUID) -> BacklogVersion | None:
        record = self._session.scalars(
            select(VersionRecord).where(VersionRecord.run_id == run_id)
        ).one_or_none()
        return None if record is None else self._to_version(record)

    def find_id_by_run(self, run_id: UUID) -> BacklogVersionId | None:
        version_id = self._session.scalar(
            select(VersionRecord.id).where(VersionRecord.run_id == run_id)
        )
        return None if version_id is None else BacklogVersionId(version_id)

    def add(self, version: BacklogVersion) -> None:
        self._session.add(
            VersionRecord(
                id=version.id,
                project_id=version.project_id,
                base_version_id=version.base_version_id,
                revision=version.revision,
                state=version.state,
                content_hash=version.content_hash,
                schema_version=PAYLOAD_SCHEMA_VERSION,
                run_id=version.run_id,
                source_version_ids=[str(v) for v in version.source_version_ids],
                decisions=[_decision_json(decision) for decision in version.decisions],
                out_of_scope=[
                    {
                        "kind": note.kind,
                        "summary": note.summary,
                        "evidence": _evidence_json(note.evidence),
                    }
                    for note in version.out_of_scope
                ],
                created_by=version.created_by,
                created_at=version.created_at,
            )
        )
        # The version row must exist before the item rows that reference it.
        self._session.flush()
        self._session.add_all(
            ItemRevisionRecord(
                id=new_id(),
                version_id=version.id,
                item_id=item.id,
                position=position,
                kind=item.kind,
                parent_item_id=item.parent_id,
                title=item.title,
                payload=_item_json(item),
            )
            for position, item in enumerate(version.items)
        )
        self._session.flush()

    def _to_version(self, record: VersionRecord) -> BacklogVersion:
        items = self._session.scalars(
            select(ItemRevisionRecord)
            .where(ItemRevisionRecord.version_id == record.id)
            .order_by(ItemRevisionRecord.position)
        )
        return BacklogVersion(
            id=BacklogVersionId(record.id),
            project_id=ProjectId(record.project_id),
            base_version_id=None
            if record.base_version_id is None
            else BacklogVersionId(record.base_version_id),
            revision=record.revision,
            state=record.state,
            content_hash=record.content_hash,
            run_id=record.run_id,
            source_version_ids=tuple(UUID(v) for v in record.source_version_ids),
            items=tuple(_to_item(item) for item in items),
            decisions=tuple(_to_decision(decision) for decision in record.decisions),
            out_of_scope=tuple(
                ScopeNote(note["kind"], note["summary"], _to_evidence(note["evidence"]))
                for note in record.out_of_scope
            ),
            created_by=UserId(record.created_by),
            created_at=record.created_at,
        )


def _evidence_json(evidence: Sequence[Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "source_version_id": str(e.source_version_id),
            "block_id": str(e.block_id),
            "quote": e.quote,
            "relationship": e.relationship,
        }
        for e in evidence
    ]


def _to_evidence(data: Sequence[Mapping[str, Any]]) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(UUID(e["source_version_id"]), UUID(e["block_id"]), e["quote"], e["relationship"])
        for e in data
    )


def _item_json(item: Item) -> dict[str, Any]:
    return {
        "description": item.description,
        "criteria": [
            {
                "id": str(criterion.id),
                "text": criterion.text,
                "origin": criterion.origin,
                "evidence": _evidence_json(criterion.evidence),
                "confirmed_by": [str(decision_id) for decision_id in criterion.confirmed_by],
            }
            for criterion in item.criteria
        ],
        "assumptions": list(item.assumptions),
        "open_questions": list(item.open_questions),
        "human_edited": item.human_edited,
    }


def _to_item(record: ItemRevisionRecord) -> Item:
    payload = record.payload
    return Item(
        id=ItemId(record.item_id),
        kind="epic" if record.kind == "epic" else "story",
        parent_id=None if record.parent_item_id is None else ItemId(record.parent_item_id),
        title=record.title,
        description=payload["description"],
        criteria=tuple(
            Criterion(
                id=CriterionId(UUID(criterion["id"])),
                text=criterion["text"],
                origin=criterion["origin"],
                evidence=_to_evidence(criterion["evidence"]),
                confirmed_by=tuple(DecisionId(UUID(d)) for d in criterion["confirmed_by"]),
            )
            for criterion in payload["criteria"]
        ),
        assumptions=tuple(payload["assumptions"]),
        open_questions=tuple(payload["open_questions"]),
        human_edited=payload["human_edited"],
    )


def _decision_json(decision: Decision) -> dict[str, Any]:
    return {
        "id": str(decision.id),
        "kind": decision.kind,
        "status": decision.status,
        "subject": decision.subject,
        "question": decision.question,
        "why_it_matters": decision.why_it_matters,
        "evidence": _evidence_json(decision.evidence),
        "affected_item_ids": [str(item_id) for item_id in decision.affected_item_ids],
        "question_id": None if decision.question_id is None else str(decision.question_id),
        "answer": decision.answer,
        "decided_by": None if decision.decided_by is None else str(decision.decided_by),
        "decided_at": None if decision.decided_at is None else decision.decided_at.isoformat(),
    }


def _to_decision(data: Mapping[str, Any]) -> Decision:
    return Decision(
        id=DecisionId(UUID(data["id"])),
        kind=data["kind"],
        status=data["status"],
        subject=data["subject"],
        question=data["question"],
        why_it_matters=data["why_it_matters"],
        evidence=_to_evidence(data["evidence"]),
        affected_item_ids=tuple(ItemId(UUID(i)) for i in data["affected_item_ids"]),
        question_id=None if data["question_id"] is None else UUID(data["question_id"]),
        answer=data["answer"],
        decided_by=None if data["decided_by"] is None else UserId(UUID(data["decided_by"])),
        decided_at=None
        if data["decided_at"] is None
        else datetime.fromisoformat(data["decided_at"]),
    )

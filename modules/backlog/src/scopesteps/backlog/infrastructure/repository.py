from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, or_, select, update
from sqlalchemy.orm import Session

from scopesteps.backlog.application.editing import Receipt
from scopesteps.backlog.domain.history import ListCursor, VersionListing
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.status import VersionHeader
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Criterion,
    Decision,
    Evidence,
    Item,
    ScopeNote,
    VersionState,
    approved_content,
)
from scopesteps.backlog.infrastructure.orm import (
    CommandReceiptRecord,
    ItemRevisionRecord,
    VersionRecord,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

# v2 adds suggestion review and who edited what. A v1 payload reads as one nobody edited, with
# its proposed criteria still pending review.
PAYLOAD_SCHEMA_VERSION = "backlog-version.v2"


class SqlVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, version_id: BacklogVersionId) -> BacklogVersion | None:
        record = self._session.get(VersionRecord, version_id, populate_existing=True)
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

    def headers_by_project(
        self, project_ids: Collection[ProjectId]
    ) -> dict[ProjectId, list[VersionHeader]]:
        """One query for all the projects; projects without versions are absent."""
        rows = self._session.execute(
            select(
                VersionRecord.project_id,
                VersionRecord.id,
                VersionRecord.state,
                VersionRecord.created_at,
            ).where(VersionRecord.project_id.in_(list(project_ids)))
        )
        headers: dict[ProjectId, list[VersionHeader]] = {}
        for project_id, version_id, state, created_at in rows:
            headers.setdefault(ProjectId(project_id), []).append(
                VersionHeader(BacklogVersionId(version_id), state, created_at)
            )
        return headers

    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[VersionListing]:
        """Version rows only, without items, so a page costs one query."""
        query = select(
            VersionRecord.id,
            VersionRecord.state,
            VersionRecord.revision,
            VersionRecord.content_hash,
            VersionRecord.base_version_id,
            VersionRecord.run_id,
            VersionRecord.created_by,
            VersionRecord.created_at,
        ).where(VersionRecord.project_id == project_id)
        if after is not None:
            query = query.where(
                or_(
                    VersionRecord.created_at < after.created_at,
                    and_(VersionRecord.created_at == after.created_at, VersionRecord.id < after.id),
                )
            )
        rows = self._session.execute(
            query.order_by(VersionRecord.created_at.desc(), VersionRecord.id.desc()).limit(limit)
        )
        return [
            VersionListing(
                id=BacklogVersionId(version_id),
                state=state,
                revision=revision,
                content_hash=hash_,
                base_version_id=None if base_id is None else BacklogVersionId(base_id),
                run_id=run_id,
                created_by=UserId(created_by),
                created_at=created_at,
            )
            for version_id, state, revision, hash_, base_id, run_id, created_by, created_at in rows
        ]

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

    def save_item(
        self, version: BacklogVersion, item: Item, *, expected_revision: int, content_hash: str
    ) -> bool:
        """Store `item` in the draft and move the version to its next revision. False, changing
        nothing, if the version is no longer a draft at `expected_revision`."""
        if not self._advance(
            version.id,
            expected_revision=expected_revision,
            values={"revision": expected_revision + 1, "content_hash": content_hash},
        ):
            return False
        self._session.execute(
            update(ItemRevisionRecord)
            .where(
                ItemRevisionRecord.version_id == version.id,
                ItemRevisionRecord.item_id == item.id,
            )
            .values(title=item.title, payload=_item_json(item))
            .execution_options(synchronize_session=False)
        )
        return True

    def save_decisions(
        self,
        version: BacklogVersion,
        decisions: tuple[Decision, ...],
        *,
        expected_revision: int,
        content_hash: str,
    ) -> bool:
        """Store the draft's decisions and move it to its next revision. False, changing nothing,
        if the version is no longer a draft at `expected_revision`."""
        return self._advance(
            version.id,
            expected_revision=expected_revision,
            values={
                "revision": expected_revision + 1,
                "content_hash": content_hash,
                "decisions": [_decision_json(decision) for decision in decisions],
            },
        )

    def freeze_approved(
        self, version_id: BacklogVersionId, *, expected_revision: int, content_hash: str
    ) -> bool:
        """Mark the draft approved and drop its rejected suggestions, keeping its revision and
        hash. False, changing nothing, if it is no longer a draft at that revision and hash."""
        version = self.get(version_id)
        if version is None or not self._advance(
            version_id,
            expected_revision=expected_revision,
            expected_hash=content_hash,
            values={"state": VersionState.APPROVED},
        ):
            return False
        for before, after in zip(version.items, approved_content(version.items), strict=True):
            if after != before:
                self._session.execute(
                    update(ItemRevisionRecord)
                    .where(
                        ItemRevisionRecord.version_id == version_id,
                        ItemRevisionRecord.item_id == after.id,
                    )
                    .values(payload=_item_json(after))
                    .execution_options(synchronize_session=False)
                )
        return True

    def mark_rejected(self, version_id: BacklogVersionId, *, expected_revision: int) -> bool:
        return self._advance(
            version_id,
            expected_revision=expected_revision,
            values={"state": VersionState.REJECTED},
        )

    def _advance(
        self,
        version_id: BacklogVersionId,
        *,
        expected_revision: int,
        values: dict[str, Any],
        expected_hash: str | None = None,
    ) -> bool:
        # The state and revision are compared in the UPDATE itself, so of two writers holding the
        # same revision exactly one succeeds, and nothing changes a version that left the draft
        # state.
        conditions = [
            VersionRecord.id == version_id,
            VersionRecord.revision == expected_revision,
            VersionRecord.state == VersionState.DRAFT,
        ]
        if expected_hash is not None:
            conditions.append(VersionRecord.content_hash == expected_hash)
        result = self._session.execute(
            update(VersionRecord)
            .where(*conditions)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

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
                "suggestion": criterion.suggestion,
                "edited_by": _optional_str(criterion.edited_by),
            }
            for criterion in item.criteria
        ],
        "assumptions": list(item.assumptions),
        "open_questions": list(item.open_questions),
        "human_edited": item.human_edited,
        "edited_by": _optional_str(item.edited_by),
        "edited_at": None if item.edited_at is None else item.edited_at.isoformat(),
    }


def _optional_str(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _optional_user(value: str | None) -> UserId | None:
    return None if value is None else UserId(UUID(value))


def _suggestion(criterion: Mapping[str, Any]) -> Any:
    if "suggestion" in criterion:
        return criterion["suggestion"]
    return "pending" if criterion["origin"] == "proposed" else None


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
                suggestion=_suggestion(criterion),
                edited_by=_optional_user(criterion.get("edited_by")),
            )
            for criterion in payload["criteria"]
        ),
        assumptions=tuple(payload["assumptions"]),
        open_questions=tuple(payload["open_questions"]),
        human_edited=payload["human_edited"],
        edited_by=_optional_user(payload.get("edited_by")),
        edited_at=None
        if payload.get("edited_at") is None
        else datetime.fromisoformat(payload["edited_at"]),
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


class SqlReceiptStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        record = self._session.scalars(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.actor_id == actor_id,
                CommandReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return Receipt(
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            version_id=BacklogVersionId(record.version_id),
            fingerprint=record.fingerprint,
            created_at=record.created_at,
        )

    def add(self, receipt: Receipt) -> None:
        self._session.add(
            CommandReceiptRecord(
                id=new_id(),
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                version_id=receipt.version_id,
                fingerprint=receipt.fingerprint,
                created_at=receipt.created_at,
            )
        )
        # Fails here, not at commit, when a concurrent request already used the key.
        self._session.flush()

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Select, and_, func, select, update
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.upload import UploadReceipt
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import (
    Source,
    SourceBlock,
    SourceKind,
    SourceVersion,
    SpeakerLabel,
)
from scopesteps.sources.infrastructure.orm import (
    SourceBlockRecord,
    SourceRecord,
    SourceVersionRecord,
    SpeakerLabelRecord,
    UploadReceiptRecord,
)

_VERSION_WITH_SOURCE = select(SourceVersionRecord, SourceRecord).join(
    SourceRecord, SourceRecord.id == SourceVersionRecord.source_id
)


class SqlSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_receipt(
        self, project_id: ProjectId, actor_id: UserId, idempotency_key: str
    ) -> UploadReceipt | None:
        record = self._session.scalars(
            select(UploadReceiptRecord).where(
                UploadReceiptRecord.project_id == project_id,
                UploadReceiptRecord.actor_id == actor_id,
                UploadReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return UploadReceipt(
            project_id=ProjectId(record.project_id),
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            fingerprint=record.fingerprint,
            source_version_ids=tuple(
                SourceVersionId(UUID(version_id)) for version_id in record.source_version_ids
            ),
            created_at=record.created_at,
        )

    def add_receipt(self, receipt: UploadReceipt) -> None:
        self._session.add(
            UploadReceiptRecord(
                id=new_id(),
                project_id=receipt.project_id,
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                fingerprint=receipt.fingerprint,
                source_version_ids=[str(version_id) for version_id in receipt.source_version_ids],
                created_at=receipt.created_at,
            )
        )

    def get_versions(self, version_ids: Sequence[SourceVersionId]) -> list[SourceVersion]:
        rows = self._session.execute(
            _VERSION_WITH_SOURCE.where(SourceVersionRecord.id.in_(version_ids))
        )
        by_id = {version.id: _to_version(version, source) for version, source in rows}
        return [by_id[version_id] for version_id in version_ids]

    def latest_version_of(self, source_id: SourceId) -> SourceVersion:
        row = self._session.execute(
            _VERSION_WITH_SOURCE.where(SourceVersionRecord.source_id == source_id)
            .order_by(SourceVersionRecord.version.desc())
            .limit(1)
        ).one()
        return _to_version(*row)

    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None:
        record = self._session.scalars(
            select(SourceRecord).where(
                SourceRecord.id == source_id, SourceRecord.project_id == project_id
            )
        ).one_or_none()
        return None if record is None else _to_source(record)

    def next_source_number(self, project_id: ProjectId) -> int:
        highest = self._session.scalar(
            select(func.max(SourceRecord.number)).where(SourceRecord.project_id == project_id)
        )
        return (highest or 0) + 1

    def version_ids(self, source_id: SourceId) -> list[SourceVersionId]:
        return [
            SourceVersionId(version_id)
            for version_id in self._session.scalars(
                select(SourceVersionRecord.id).where(SourceVersionRecord.source_id == source_id)
            )
        ]

    def removed_version_ids(
        self, project_id: ProjectId, version_ids: Collection[SourceVersionId]
    ) -> set[SourceVersionId]:
        rows = self._session.scalars(
            select(SourceVersionRecord.id)
            .join(SourceRecord, SourceRecord.id == SourceVersionRecord.source_id)
            .where(
                SourceRecord.project_id == project_id,
                SourceRecord.removed_at.is_not(None),
                SourceVersionRecord.id.in_(list(version_ids)),
            )
        )
        return {SourceVersionId(version_id) for version_id in rows}

    def mark_removed(self, source_id: SourceId, removed_by: UserId, removed_at: datetime) -> bool:
        result = self._session.execute(
            update(SourceRecord)
            .where(SourceRecord.id == source_id, SourceRecord.removed_at.is_(None))
            .values(removed_at=removed_at, removed_by=removed_by)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        rows = self._session.execute(self._current_in([project_id]).order_by(SourceRecord.number))
        return [_to_version(version, source) for version, source in rows]

    def current_transcripts(
        self, project_ids: Collection[ProjectId]
    ) -> list[tuple[Source, SourceVersion, bool]]:
        """Each current transcript of the projects in one query, in source order per project,
        with whether its speakers were looked for when it was stored."""
        rows = self._session.execute(
            self._current_in(project_ids)
            .where(SourceRecord.kind == SourceKind.TRANSCRIPT)
            .order_by(SourceRecord.project_id, SourceRecord.number)
        )
        return [
            (
                _to_source(source),
                _to_version(version, source),
                version.speakers_detected_at is not None,
            )
            for version, source in rows
        ]

    def _current_in(
        self, project_ids: Collection[ProjectId]
    ) -> Select[SourceVersionRecord, SourceRecord]:
        latest = (
            select(
                SourceVersionRecord.source_id,
                func.max(SourceVersionRecord.version).label("version"),
            )
            .group_by(SourceVersionRecord.source_id)
            .subquery()
        )
        return _VERSION_WITH_SOURCE.join(
            latest,
            and_(
                latest.c.source_id == SourceVersionRecord.source_id,
                latest.c.version == SourceVersionRecord.version,
            ),
        ).where(
            SourceRecord.project_id.in_(list(project_ids)),
            SourceRecord.removed_at.is_(None),
            SourceRecord.kind != SourceKind.CHANGE_REQUEST,
        )

    def get_version(
        self, project_id: ProjectId, version_id: SourceVersionId
    ) -> SourceVersion | None:
        row = self._session.execute(
            _VERSION_WITH_SOURCE.where(
                SourceVersionRecord.id == version_id, SourceRecord.project_id == project_id
            )
        ).one_or_none()
        return None if row is None else _to_version(*row)

    def blocks(self, version_id: SourceVersionId) -> list[SourceBlock]:
        records = self._session.scalars(
            select(SourceBlockRecord)
            .where(SourceBlockRecord.source_version_id == version_id)
            .order_by(SourceBlockRecord.ordinal)
        )
        return [
            SourceBlock(
                id=SourceBlockId(record.id),
                source_version_id=SourceVersionId(record.source_version_id),
                ordinal=record.ordinal,
                text=record.text,
                start_offset=record.start_offset,
                end_offset=record.end_offset,
            )
            for record in records
        ]

    def version_text(self, version_id: SourceVersionId) -> str:
        return self._session.scalars(
            select(SourceVersionRecord.text).where(SourceVersionRecord.id == version_id)
        ).one()

    def speaker_labels(self, version_id: SourceVersionId) -> list[SpeakerLabel] | None:
        detected_at = self._session.scalars(
            select(SourceVersionRecord.speakers_detected_at).where(
                SourceVersionRecord.id == version_id
            )
        ).one()
        if detected_at is None:
            return None
        rows = self._session.execute(
            select(SpeakerLabelRecord, SourceBlockRecord.ordinal)
            .join(SourceBlockRecord, SourceBlockRecord.id == SpeakerLabelRecord.first_block_id)
            .where(SpeakerLabelRecord.source_version_id == version_id)
            .order_by(SpeakerLabelRecord.position)
        )
        return [_to_label(record, ordinal) for record, ordinal in rows]

    def stored_speaker_labels(
        self, version_ids: Collection[SourceVersionId]
    ) -> dict[SourceVersionId, list[SpeakerLabel]]:
        """The stored labels of every version given in one query; a version without any is
        absent."""
        rows = self._session.execute(
            select(SpeakerLabelRecord, SourceBlockRecord.ordinal)
            .join(SourceBlockRecord, SourceBlockRecord.id == SpeakerLabelRecord.first_block_id)
            .where(SpeakerLabelRecord.source_version_id.in_(list(version_ids)))
            .order_by(SpeakerLabelRecord.source_version_id, SpeakerLabelRecord.position)
        )
        found: dict[SourceVersionId, list[SpeakerLabel]] = {}
        for record, ordinal in rows:
            found.setdefault(SourceVersionId(record.source_version_id), []).append(
                _to_label(record, ordinal)
            )
        return found

    def add_speaker_labels(
        self, version_id: SourceVersionId, labels: Sequence[SpeakerLabel], detected_at: datetime
    ) -> None:
        self._session.add_all(
            SpeakerLabelRecord(
                id=new_id(),
                source_version_id=version_id,
                position=position,
                label=label.label,
                key=label.key,
                turn_count=label.turn_count,
                first_block_id=label.first_block_id,
                sample=label.sample,
            )
            for position, label in enumerate(labels)
        )
        self._session.execute(
            update(SourceVersionRecord)
            .where(SourceVersionRecord.id == version_id)
            .values(speakers_detected_at=detected_at)
            .execution_options(synchronize_session=False)
        )

    def add_source(self, source: Source) -> None:
        self._session.add(
            SourceRecord(
                id=source.id,
                project_id=source.project_id,
                kind=source.kind,
                number=source.number,
                created_at=source.created_at,
            )
        )
        # Versions reference the source, and nothing tells the unit of work to order the inserts.
        self._session.flush()

    def add_version(self, version: SourceVersion, text: str, blocks: Sequence[SourceBlock]) -> None:
        self._session.add(
            SourceVersionRecord(
                id=version.id,
                source_id=version.source_id,
                version=version.version,
                filename=version.filename,
                media_type=version.media_type,
                checksum_sha256=version.checksum_sha256,
                byte_size=version.byte_size,
                word_count=version.word_count,
                block_count=version.block_count,
                text=text,
                uploaded_by=version.uploaded_by,
                created_at=version.created_at,
            )
        )
        self._session.flush()
        self._session.add_all(
            SourceBlockRecord(
                id=block.id,
                source_version_id=block.source_version_id,
                ordinal=block.ordinal,
                text=block.text,
                start_offset=block.start_offset,
                end_offset=block.end_offset,
            )
            for block in blocks
        )
        self._session.flush()


def _to_version(record: SourceVersionRecord, source: SourceRecord) -> SourceVersion:
    return SourceVersion(
        id=SourceVersionId(record.id),
        source_id=SourceId(record.source_id),
        project_id=ProjectId(source.project_id),
        kind=source.kind,
        source_number=source.number,
        version=record.version,
        filename=record.filename,
        media_type=record.media_type,
        checksum_sha256=record.checksum_sha256,
        byte_size=record.byte_size,
        word_count=record.word_count,
        block_count=record.block_count,
        uploaded_by=UserId(record.uploaded_by),
        created_at=record.created_at,
    )


def _to_label(record: SpeakerLabelRecord, first_block_ordinal: int) -> SpeakerLabel:
    return SpeakerLabel(
        source_version_id=SourceVersionId(record.source_version_id),
        label=record.label,
        key=record.key,
        turn_count=record.turn_count,
        first_block_id=SourceBlockId(record.first_block_id),
        first_block_ordinal=first_block_ordinal,
        sample=record.sample,
    )


def _to_source(record: SourceRecord) -> Source:
    return Source(
        id=SourceId(record.id),
        project_id=ProjectId(record.project_id),
        kind=record.kind,
        number=record.number,
        created_at=record.created_at,
        removed_at=record.removed_at,
        removed_by=None if record.removed_by is None else UserId(record.removed_by),
    )

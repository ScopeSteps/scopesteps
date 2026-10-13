from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.upload import UploadReceipt
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import Source, SourceBlock, SourceKind, SourceVersion
from scopesteps.sources.infrastructure.orm import (
    SourceBlockRecord,
    SourceRecord,
    SourceVersionRecord,
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

    def latest_version(self, project_id: ProjectId, kind: SourceKind) -> SourceVersion | None:
        row = self._session.execute(
            _VERSION_WITH_SOURCE.where(
                SourceRecord.project_id == project_id, SourceRecord.kind == kind
            )
            .order_by(SourceVersionRecord.version.desc())
            .limit(1)
        ).one_or_none()
        return None if row is None else _to_version(*row)

    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        latest = (
            select(
                SourceVersionRecord.source_id,
                func.max(SourceVersionRecord.version).label("version"),
            )
            .group_by(SourceVersionRecord.source_id)
            .subquery()
        )
        rows = self._session.execute(
            _VERSION_WITH_SOURCE.join(
                latest,
                and_(
                    latest.c.source_id == SourceVersionRecord.source_id,
                    latest.c.version == SourceVersionRecord.version,
                ),
            )
            .where(SourceRecord.project_id == project_id)
            .order_by(SourceRecord.kind)
        )
        return [_to_version(version, source) for version, source in rows]

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

    def add_source(self, source: Source) -> None:
        self._session.add(
            SourceRecord(
                id=source.id,
                project_id=source.project_id,
                kind=source.kind,
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


def _to_version(record: SourceVersionRecord, source: SourceRecord) -> SourceVersion:
    return SourceVersion(
        id=SourceVersionId(record.id),
        source_id=SourceId(record.source_id),
        project_id=ProjectId(source.project_id),
        kind=source.kind,
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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.client import ProjectAccess, Role, UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.sources.domain.errors import IdempotencyKeyReusedError
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import Source, SourceBlock, SourceKind, SourceVersion
from scopesteps.sources.domain.upload import (
    ParsedSource,
    SourceLimits,
    UploadedFile,
    parse_uploads,
    request_fingerprint,
)


@dataclass(frozen=True)
class UploadSources:
    idempotency_key: str
    files: tuple[UploadedFile, ...]


@dataclass(frozen=True)
class UploadReceipt:
    """What an accepted upload command produced, kept so a retry returns the same versions."""

    project_id: ProjectId
    actor_id: UserId
    idempotency_key: str
    fingerprint: str
    source_version_ids: tuple[SourceVersionId, ...]
    created_at: datetime


class SourceWriter(Protocol):
    def find_receipt(
        self, project_id: ProjectId, actor_id: UserId, idempotency_key: str
    ) -> UploadReceipt | None: ...

    def add_receipt(self, receipt: UploadReceipt) -> None: ...

    def get_versions(self, version_ids: Sequence[SourceVersionId]) -> list[SourceVersion]:
        """Versions in the order of `version_ids`."""
        ...

    def latest_version(self, project_id: ProjectId, kind: SourceKind) -> SourceVersion | None: ...

    def add_source(self, source: Source) -> None: ...

    def add_version(
        self, version: SourceVersion, text: str, blocks: Sequence[SourceBlock]
    ) -> None: ...


def upload_sources(
    store: SourceWriter,
    access: ProjectAccess,
    command: UploadSources,
    limits: SourceLimits,
    now: datetime,
) -> list[SourceVersion]:
    """Accept every file or none. Returns one version per file, in the order given."""
    access.require_role(Role.EDITOR)

    fingerprint = request_fingerprint(command.files)
    receipt = store.find_receipt(access.project_id, access.actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.fingerprint != fingerprint:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for a different upload"
            )
        return store.get_versions(receipt.source_version_ids)

    parsed = parse_uploads(command.files, limits)
    versions = [_accept(store, access, source, now) for source in parsed]
    store.add_receipt(
        UploadReceipt(
            project_id=access.project_id,
            actor_id=access.actor.user_id,
            idempotency_key=command.idempotency_key,
            fingerprint=fingerprint,
            source_version_ids=tuple(version.id for version in versions),
            created_at=now,
        )
    )
    return versions


def _accept(
    store: SourceWriter, access: ProjectAccess, parsed: ParsedSource, now: datetime
) -> SourceVersion:
    latest = store.latest_version(access.project_id, parsed.kind)
    # A version identifies content: uploading unchanged bytes again must not mint a new one,
    # or citations to the same passage would be split across versions.
    if latest is not None and latest.checksum_sha256 == parsed.checksum_sha256:
        return latest

    if latest is None:
        source_id = SourceId(new_id())
        store.add_source(
            Source(id=source_id, project_id=access.project_id, kind=parsed.kind, created_at=now)
        )
    else:
        source_id = latest.source_id

    version = SourceVersion(
        id=SourceVersionId(new_id()),
        source_id=source_id,
        project_id=access.project_id,
        kind=parsed.kind,
        version=latest.version + 1 if latest else 1,
        filename=parsed.filename,
        media_type=parsed.media_type,
        checksum_sha256=parsed.checksum_sha256,
        byte_size=parsed.byte_size,
        word_count=parsed.word_count,
        block_count=len(parsed.blocks),
        uploaded_by=access.actor.user_id,
        created_at=now,
    )
    blocks = [
        SourceBlock(
            id=SourceBlockId(new_id()),
            source_version_id=version.id,
            ordinal=block.ordinal,
            text=block.text,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
        )
        for block in parsed.blocks
    ]
    store.add_version(version, parsed.text, blocks)
    return version

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId
from scopesteps.sources.domain.errors import (
    IdempotencyKeyReusedError,
    NoSourceFilesError,
    SourceRemovedError,
    TooManySourceFilesError,
)
from scopesteps.sources.domain.ids import SourceBlockId, SourceId, SourceVersionId
from scopesteps.sources.domain.source import Source, SourceBlock, SourceVersion
from scopesteps.sources.domain.upload import (
    ParsedSource,
    SourceLimits,
    UploadedFile,
    check_word_limit,
    parse_uploads,
    request_fingerprint,
)

# Every file is read into memory before validation, so this bounds one request's memory at this
# many times the per-file size limit. The word limit allows far fewer useful files anyway.
MAX_FILES_PER_UPLOAD = 20


@dataclass(frozen=True)
class UploadSources:
    idempotency_key: str
    files: tuple[UploadedFile, ...]


@dataclass(frozen=True)
class AddSourceVersion:
    """Corrected content for an existing source: it becomes the source's next version."""

    idempotency_key: str
    source_id: SourceId
    filename: str
    content: bytes


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

    def current_versions(self, project_id: ProjectId) -> list[SourceVersion]:
        """The latest version of each source the project has not removed."""
        ...

    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None:
        """None unless the source belongs to `project_id`. Removed sources are returned too."""
        ...

    def latest_version_of(self, source_id: SourceId) -> SourceVersion: ...

    def next_source_number(self, project_id: ProjectId) -> int:
        """One more than the highest number any of the project's sources, removed or not, has."""
        ...

    def add_source(self, source: Source) -> None: ...

    def add_version(
        self, version: SourceVersion, text: str, blocks: Sequence[SourceBlock]
    ) -> None: ...


# Long enough for any ordinary filename; a longer one is shortened so the summary stays one
# short line.
MAX_SUMMARY_FILENAME_CHARS = 120


def upload_sources(
    store: SourceWriter,
    audit: AuditRecorder,
    access: ProjectAccess,
    command: UploadSources,
    limits: SourceLimits,
    now: datetime,
) -> list[SourceVersion]:
    """Accept every file or none. Returns one version per file, in the order given.

    Each file becomes a new source, except that content identical to the current version of one
    of the project's sources (or to an earlier file of the same upload) returns that version.
    Each version this call creates is recorded in the activity log; a retried command and
    unchanged content create none.
    """
    access.require_role(Role.EDITOR)
    if not command.files:
        raise NoSourceFilesError("Choose at least one file to upload")
    if len(command.files) > MAX_FILES_PER_UPLOAD:
        raise TooManySourceFilesError(
            f"Upload at most {MAX_FILES_PER_UPLOAD} files at a time",
            details={"max_files": MAX_FILES_PER_UPLOAD},
        )

    fingerprint = request_fingerprint(command.files)
    replayed = _replay(store, access, command.idempotency_key, fingerprint)
    if replayed is not None:
        return replayed

    parsed = parse_uploads(command.files, limits)
    current = store.current_versions(access.project_id)
    existing = {version.checksum_sha256: version for version in current}
    new_by_checksum = {
        source.checksum_sha256: source
        for source in parsed
        if source.checksum_sha256 not in existing
    }
    check_word_limit(
        sum(version.word_count for version in current),
        sum(source.word_count for source in new_by_checksum.values()),
        limits,
    )

    number = store.next_source_number(access.project_id)
    versions: list[SourceVersion] = []
    for source in parsed:
        version = existing.get(source.checksum_sha256)
        if version is None:
            version = _add_source(store, audit, access, source, number, now)
            existing[version.checksum_sha256] = version
            number += 1
        versions.append(version)
    _add_receipt(store, access, command.idempotency_key, fingerprint, versions, now)
    return versions


def add_source_version(
    store: SourceWriter,
    audit: AuditRecorder,
    access: ProjectAccess,
    command: AddSourceVersion,
    limits: SourceLimits,
    now: datetime,
) -> SourceVersion:
    """Store corrected content as the source's next version; earlier versions stay readable.

    Content identical to the current version returns it. The word limit counts the new version
    in place of the current one.
    """
    access.require_role(Role.EDITOR)
    source = store.get_source(access.project_id, command.source_id)
    if source is None:
        raise NotFoundError("Source not found")

    file = UploadedFile(kind=source.kind, filename=command.filename, content=command.content)
    fingerprint = request_fingerprint([file], target=str(source.id))
    replayed = _replay(store, access, command.idempotency_key, fingerprint)
    if replayed is not None:
        return replayed[0]
    if source.is_removed:
        raise SourceRemovedError(
            "This source was removed from the project, so it cannot get a new version",
            details={"source_id": str(source.id)},
        )

    (parsed,) = parse_uploads([file], limits)
    latest = store.latest_version_of(source.id)
    if latest.checksum_sha256 == parsed.checksum_sha256:
        version = latest
    else:
        current_words = sum(v.word_count for v in store.current_versions(access.project_id))
        check_word_limit(current_words - latest.word_count, parsed.word_count, limits)
        version = _add_version(store, audit, access, source, parsed, latest.version + 1, now)
    _add_receipt(store, access, command.idempotency_key, fingerprint, [version], now)
    return version


def _replay(
    store: SourceWriter, access: ProjectAccess, idempotency_key: str, fingerprint: str
) -> list[SourceVersion] | None:
    receipt = store.find_receipt(access.project_id, access.actor.user_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise IdempotencyKeyReusedError(
            "This Idempotency-Key was already used for a different upload"
        )
    return store.get_versions(receipt.source_version_ids)


def _add_receipt(
    store: SourceWriter,
    access: ProjectAccess,
    idempotency_key: str,
    fingerprint: str,
    versions: Sequence[SourceVersion],
    now: datetime,
) -> None:
    store.add_receipt(
        UploadReceipt(
            project_id=access.project_id,
            actor_id=access.actor.user_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            source_version_ids=tuple(version.id for version in versions),
            created_at=now,
        )
    )


def _add_source(
    store: SourceWriter,
    audit: AuditRecorder,
    access: ProjectAccess,
    parsed: ParsedSource,
    number: int,
    now: datetime,
) -> SourceVersion:
    source = Source(
        id=SourceId(new_id()),
        project_id=access.project_id,
        kind=parsed.kind,
        number=number,
        created_at=now,
    )
    store.add_source(source)
    return _add_version(store, audit, access, source, parsed, 1, now)


def _add_version(
    store: SourceWriter,
    audit: AuditRecorder,
    access: ProjectAccess,
    source: Source,
    parsed: ParsedSource,
    number: int,
    now: datetime,
) -> SourceVersion:
    version = SourceVersion(
        id=SourceVersionId(new_id()),
        source_id=source.id,
        project_id=access.project_id,
        kind=source.kind,
        source_number=source.number,
        version=number,
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
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.SOURCE_ADDED,
        subjects=(
            Subject(SubjectKind.SOURCE, source.id),
            Subject(SubjectKind.SOURCE_VERSION, version.id),
        ),
        summary=(
            f"Added the {source.kind.label} {short_filename(parsed.filename)} "
            f"(version {version.version})"
        ),
        occurred_at=now,
    )
    return version


def short_filename(filename: str) -> str:
    if len(filename) <= MAX_SUMMARY_FILENAME_CHARS:
        return filename
    return filename[: MAX_SUMMARY_FILENAME_CHARS - 1] + "…"

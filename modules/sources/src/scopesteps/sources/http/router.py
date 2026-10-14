from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.audit.client import audit_recorder
from scopesteps.identity.client import ProjectAccess, get_project_access
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, IdempotencyKey, SessionDep
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application import reading, removal, upload
from scopesteps.sources.client import (
    SourceId,
    SourceUsageReader,
    SourceVersionId,
    get_source_usage_reader,
)
from scopesteps.sources.domain.errors import ConcurrentUploadError
from scopesteps.sources.domain.source import SourceBlock, SourceKind, SourceVersion
from scopesteps.sources.domain.upload import SourceLimits, UploadedFile
from scopesteps.sources.http.schemas import (
    BlockLocator,
    RemovedSourceResponse,
    SourceBlockResponse,
    SourceListResponse,
    SourceUploadResponse,
    SourceVersionResponse,
)
from scopesteps.sources.infrastructure.repository import SqlSourceRepository

router = APIRouter(tags=["sources"])

ProjectAccessDep = Annotated[ProjectAccess, Depends(get_project_access)]


def get_source_limits(request: Request) -> SourceLimits:
    limits: SourceLimits = request.app.state.source_limits
    return limits


SourceLimitsDep = Annotated[SourceLimits, Depends(get_source_limits)]


UPLOAD_REJECTIONS: dict[int | str, dict[str, Any]] = {
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ErrorResponse,
        "description": "A file exceeds the size limit, or the project's sources the word limit",
    },
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
        "model": ErrorResponse,
        "description": "A file is not .txt or .md",
    },
}


@router.post(
    "/projects/{project_id}/sources",
    status_code=status.HTTP_201_CREATED,
    responses=UPLOAD_REJECTIONS,
)
def upload_sources(
    project_id: ProjectId,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    limits: SourceLimitsDep,
    session: SessionDep,
    brief: Annotated[
        list[UploadFile] | None, File(description="Project briefs: UTF-8 .txt or .md files")
    ] = None,
    transcript: Annotated[
        list[UploadFile] | None,
        File(description="Meeting transcripts: UTF-8 .txt or .md files"),
    ] = None,
    supporting_document: Annotated[
        list[UploadFile] | None,
        File(description="Any other supporting documents: UTF-8 .txt or .md files"),
    ] = None,
) -> SourceUploadResponse:
    """Store each file as a new source, or none of them. The part name is the file's kind; send
    one or more parts in any combination.

    A file identical to the current version of one of the project's sources returns that version
    instead. The word limit counts the project's current sources plus the new files. Versions are
    returned in the order brief, transcript, supporting_document, each in the order sent.
    """
    parts = [
        (kind, file)
        for kind, files in (
            (SourceKind.BRIEF, brief),
            (SourceKind.TRANSCRIPT, transcript),
            (SourceKind.SUPPORTING_DOCUMENT, supporting_document),
        )
        for file in files or []
    ]
    command = upload.UploadSources(
        idempotency_key=idempotency_key,
        files=tuple(_read(file, kind, limits) for kind, file in parts),
    )
    versions = upload.upload_sources(
        SqlSourceRepository(session), audit_recorder(session), access, command, limits, utc_now()
    )
    _commit(session)
    return SourceUploadResponse(source_versions=[_version_response(v) for v in versions])


@router.post(
    "/projects/{project_id}/sources/{source_id}/versions",
    status_code=status.HTTP_201_CREATED,
    responses=UPLOAD_REJECTIONS,
)
def add_source_version(
    project_id: ProjectId,
    source_id: SourceId,
    file: Annotated[UploadFile, File(description="Corrected content: a UTF-8 .txt or .md file")],
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    limits: SourceLimitsDep,
    session: SessionDep,
) -> SourceVersionResponse:
    """Store corrected content as the source's next version. Earlier versions stay readable, so
    their citations keep resolving. Content identical to the current version returns it."""
    content = file.file.read(limits.max_bytes + 1)
    version = upload.add_source_version(
        SqlSourceRepository(session),
        audit_recorder(session),
        access,
        upload.AddSourceVersion(
            idempotency_key=idempotency_key,
            source_id=source_id,
            filename=file.filename or "",
            content=content,
        ),
        limits,
        utc_now(),
    )
    _commit(session)
    return _version_response(version)


@router.delete("/projects/{project_id}/sources/{source_id}")
def remove_source(
    project_id: ProjectId,
    source_id: SourceId,
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    usage: Annotated[SourceUsageReader, Depends(get_source_usage_reader)],
    session: SessionDep,
) -> RemovedSourceResponse:
    """Take the source out of the project's current sources. Nothing is deleted (ADR 0009).

    409 `SOURCE_IN_USE` when a run, a backlog version or a person's evidence refers to any of its
    versions; `details.used_by` counts them by kind. Removing it again returns it unchanged.
    """
    source = removal.remove_source(
        SqlSourceRepository(session),
        audit_recorder(session),
        usage,
        access,
        source_id,
        utc_now(),
    )
    session.commit()
    return RemovedSourceResponse(
        source_id=source.id,
        project_id=source.project_id,
        kind=source.kind,
        source_number=source.number,
        removed_at=source.removed_at,
        removed_by=source.removed_by,
    )


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        # A concurrent request won a unique constraint: the same Idempotency-Key, the same next
        # source number or the same next version number. Nothing of this request was stored.
        session.rollback()
        raise ConcurrentUploadError(
            "Another upload for this project finished first. Try again."
        ) from error


@router.get("/projects/{project_id}/sources")
def list_sources(
    project_id: ProjectId, access: ProjectAccessDep, session: SessionDep
) -> SourceListResponse:
    """The current version of each of the project's sources."""
    versions = reading.list_current_sources(SqlSourceRepository(session), access)
    return SourceListResponse(source_versions=[_version_response(v) for v in versions])


@router.get("/projects/{project_id}/sources/{source_version_id}/blocks")
def list_source_blocks(
    project_id: ProjectId,
    source_version_id: SourceVersionId,
    access: ProjectAccessDep,
    session: SessionDep,
) -> list[SourceBlockResponse]:
    blocks = reading.list_source_blocks(SqlSourceRepository(session), access, source_version_id)
    return [_block_response(block) for block in blocks]


def _read(upload: UploadFile, kind: SourceKind, limits: SourceLimits) -> UploadedFile:
    # One byte past the limit is enough for validation to see the file is too large without
    # holding an arbitrarily large upload in memory.
    content = upload.file.read(limits.max_bytes + 1)
    return UploadedFile(kind=kind, filename=upload.filename or "", content=content)


def _version_response(version: SourceVersion) -> SourceVersionResponse:
    return SourceVersionResponse(
        id=version.id,
        source_id=version.source_id,
        project_id=version.project_id,
        kind=version.kind,
        source_number=version.source_number,
        version=version.version,
        filename=version.filename,
        media_type=version.media_type,
        checksum_sha256=version.checksum_sha256,
        word_count=version.word_count,
        block_count=version.block_count,
        created_at=version.created_at,
    )


def _block_response(block: SourceBlock) -> SourceBlockResponse:
    return SourceBlockResponse(
        id=block.id,
        source_version_id=block.source_version_id,
        ordinal=block.ordinal,
        text=block.text,
        locator=BlockLocator(
            paragraph=block.ordinal,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
        ),
    )

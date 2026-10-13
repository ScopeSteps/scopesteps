from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError

from scopesteps.identity.client import ProjectAccess, get_project_access
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, IdempotencyKey, SessionDep
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application import reading, upload
from scopesteps.sources.client import SourceVersionId
from scopesteps.sources.domain.errors import ConcurrentUploadError
from scopesteps.sources.domain.source import SourceBlock, SourceKind, SourceVersion
from scopesteps.sources.domain.upload import SourceLimits, UploadedFile
from scopesteps.sources.http.schemas import (
    BlockLocator,
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
        "description": "A file exceeds the size limit, or the documents the combined word limit",
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
    brief: Annotated[UploadFile, File(description="Project brief: a UTF-8 .txt or .md file")],
    transcript: Annotated[
        UploadFile, File(description="Meeting transcript: a UTF-8 .txt or .md file")
    ],
    idempotency_key: IdempotencyKey,
    access: ProjectAccessDep,
    limits: SourceLimitsDep,
    session: SessionDep,
) -> SourceUploadResponse:
    """Store both documents as immutable versions, or neither.

    Content identical to a source's current version returns that version instead of a new one.
    """
    command = upload.UploadSources(
        idempotency_key=idempotency_key,
        files=(
            _read(brief, SourceKind.BRIEF, limits),
            _read(transcript, SourceKind.TRANSCRIPT, limits),
        ),
    )
    versions = upload.upload_sources(
        SqlSourceRepository(session), access, command, limits, utc_now()
    )
    try:
        session.commit()
    except IntegrityError as error:
        # A concurrent request won a unique constraint: the same Idempotency-Key, or the same
        # next version number. Nothing of this request was stored.
        session.rollback()
        raise ConcurrentUploadError(
            "Another upload for this project finished first. Try again."
        ) from error
    return SourceUploadResponse(source_versions=[_version_response(v) for v in versions])


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

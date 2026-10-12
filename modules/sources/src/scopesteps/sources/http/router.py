from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from scopesteps.infrastructure.http import IdempotencyKey
from scopesteps.kernel.errors import FeatureNotImplementedError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId
from scopesteps.sources.http.schemas import SourceBlockResponse, SourceUploadResponse

router = APIRouter(tags=["sources"])


@router.post("/projects/{project_id}/sources", status_code=status.HTTP_201_CREATED)
def upload_sources(
    project_id: ProjectId,
    files: Annotated[list[UploadFile], File(description="UTF-8 .txt or .md files")],
    idempotency_key: IdempotencyKey,
) -> SourceUploadResponse:
    raise FeatureNotImplementedError("Source upload")


@router.get("/projects/{project_id}/sources/{source_version_id}/blocks")
def list_source_blocks(
    project_id: ProjectId, source_version_id: SourceVersionId
) -> list[SourceBlockResponse]:
    raise FeatureNotImplementedError("Source block listing")

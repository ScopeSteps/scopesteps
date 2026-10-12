from typing import Annotated, Literal

from fastapi import APIRouter, Query

from scopesteps.backlog.client import BacklogVersionId, ItemId
from scopesteps.backlog.http.schemas import (
    BacklogVersionResponse,
    ItemPatchRequest,
    ReviewRequest,
    ReviewResponse,
)
from scopesteps.infrastructure.http import IdempotencyKey
from scopesteps.kernel.errors import FeatureNotImplementedError
from scopesteps.projects.client import ProjectId

router = APIRouter(tags=["backlog"])


@router.get("/projects/{project_id}/backlogs/{version_id}")
def get_backlog_version(
    project_id: ProjectId, version_id: BacklogVersionId
) -> BacklogVersionResponse:
    raise FeatureNotImplementedError("Backlog versions")


@router.patch("/backlogs/{version_id}/items/{item_id}")
def update_backlog_item(
    version_id: BacklogVersionId,
    item_id: ItemId,
    body: ItemPatchRequest,
    idempotency_key: IdempotencyKey,
) -> BacklogVersionResponse:
    raise FeatureNotImplementedError("Backlog item editing")


@router.post("/backlogs/{version_id}/review")
def submit_for_review(
    version_id: BacklogVersionId, body: ReviewRequest, idempotency_key: IdempotencyKey
) -> ReviewResponse:
    raise FeatureNotImplementedError("Backlog review")


@router.get(
    "/backlogs/{version_id}/export",
    responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}}},
)
def export_backlog(
    version_id: BacklogVersionId,
    export_format: Annotated[Literal["json", "markdown"], Query(alias="format")] = "json",
) -> BacklogVersionResponse:
    raise FeatureNotImplementedError("Backlog export")

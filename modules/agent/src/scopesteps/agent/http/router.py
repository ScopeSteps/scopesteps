from fastapi import APIRouter, status

from scopesteps.agent.client import RunId
from scopesteps.agent.http.schemas import AnswerRequest, CreateRunRequest, RunResponse
from scopesteps.infrastructure.http import IdempotencyKey
from scopesteps.kernel.errors import FeatureNotImplementedError
from scopesteps.projects.client import ProjectId

router = APIRouter(tags=["agent"])


@router.post("/projects/{project_id}/runs", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    project_id: ProjectId, body: CreateRunRequest, idempotency_key: IdempotencyKey
) -> RunResponse:
    raise FeatureNotImplementedError("Agent runs")


@router.get("/runs/{run_id}")
def get_run(run_id: RunId) -> RunResponse:
    raise FeatureNotImplementedError("Agent runs")


@router.post("/runs/{run_id}/advance")
def advance_run(run_id: RunId, idempotency_key: IdempotencyKey) -> RunResponse:
    raise FeatureNotImplementedError("Agent runs")


@router.post("/runs/{run_id}/answers")
def answer_question(
    run_id: RunId, body: AnswerRequest, idempotency_key: IdempotencyKey
) -> RunResponse:
    raise FeatureNotImplementedError("Clarification answers")


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: RunId, idempotency_key: IdempotencyKey) -> RunResponse:
    raise FeatureNotImplementedError("Agent runs")

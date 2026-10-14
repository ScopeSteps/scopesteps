from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogItem, BacklogVersionId, ItemId
from scopesteps.change_control.client import ApprovalId, ChangeSetId
from scopesteps.identity.client import UserId


class ApproveRequest(BaseModel):
    """Approval binds to exact content: a stale revision, hash or baseline returns 409."""

    expected_revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    expected_baseline_id: BacklogVersionId | None = Field(
        description="The project's current baseline as the approver saw it; null for the first."
    )


class RejectRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class DecisionResponse(BaseModel):
    id: ApprovalId
    version_id: BacklogVersionId
    decision: Literal["approved", "rejected"]
    decided_by: UserId
    revision: int = Field(description="The draft revision the decision was made on.")
    content_hash: str
    decided_at: datetime
    baseline_version: int | None = Field(
        description="For an approval, the baseline number it created: 1 for v1, 2 for v2."
    )
    current_baseline_id: BacklogVersionId | None


class ChangeOperation(BaseModel):
    kind: Literal["add_item", "modify_item", "remove_item", "change_dependency"]
    item_id: ItemId
    rationale: str
    before: BacklogItem | None
    after: BacklogItem | None


class ChangeSetResponse(BaseModel):
    id: ChangeSetId
    base_version_id: BacklogVersionId
    candidate_version_id: BacklogVersionId
    operations: list[ChangeOperation]
    open_questions: list[str]

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.backlog.client import BacklogVersionId, DecisionId, ItemChangeResponse, ItemId
from scopesteps.change_control.client import ApprovalId, ChangeRequestId, ChangeSetId
from scopesteps.evidence.client import EvidenceRef
from scopesteps.identity.client import UserId
from scopesteps.projects.client import ProjectId
from scopesteps.sources.client import SourceVersionId


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


ChangeRequestStatus = Literal[
    "analyzing", "in_review", "no_change_needed", "approved", "rejected", "failed"
]


class DecisionResponse(BaseModel):
    id: ApprovalId
    version_id: BacklogVersionId
    decision: Literal["approved", "rejected"]
    decided_by: UserId
    revision: int = Field(description="The draft or candidate revision the decision was made on.")
    content_hash: str
    decided_at: datetime
    baseline_version: int | None = Field(
        description="For an approval, the baseline number it created: 1 for v1, 2 for v2."
    )
    current_baseline_id: BacklogVersionId | None
    change_request_id: ChangeRequestId | None = Field(
        default=None,
        description="The change request whose candidate was decided; null for a draft.",
    )
    change_request_status: ChangeRequestStatus | None = Field(
        default=None, description="The request's status after the decision: approved or rejected."
    )


class ChangeRequestAuthor(BaseModel):
    user_id: UserId
    display_name: str = Field(description="The name when the request was made.")


class ChangeSummaryResponse(BaseModel):
    """Counted from a stable-id comparison of the candidate with the baseline."""

    added: int
    changed: int
    removed: int


class ChangeRequestResponse(BaseModel):
    id: ChangeRequestId
    project_id: ProjectId
    number: int = Field(description="Shown as CR-<number>. Never reused within the project.")
    text: str
    requested_by: ChangeRequestAuthor
    requested_at: datetime
    status: ChangeRequestStatus = Field(
        description="analyzing until the change run ends; then in_review with a candidate, "
        "no_change_needed without one, or failed (the run failed or was stopped). approved and "
        "rejected follow the decision on the candidate."
    )
    base_version_id: BacklogVersionId = Field(
        description="The approved baseline the request was made against."
    )
    base_version_number: int | None = Field(description="1 for v1, 2 for v2.")
    base_content_hash: str
    source_version_id: SourceVersionId = Field(
        description="The request's text, stored as a source version the change cites."
    )
    run_id: UUID = Field(description="The change run that analyses the request.")
    candidate_version_id: BacklogVersionId | None = Field(
        description="The candidate in review the analysis proposed."
    )
    summary: ChangeSummaryResponse | None = Field(description="Set while a candidate exists.")
    analysis: str | None = Field(description="The agent's summary of the request, in its words.")
    failure: str | None = Field(description="The error code of a failed or stopped analysis.")
    analyzed_at: datetime | None
    approved_version_number: int | None = Field(
        description="The baseline number its approved candidate became (2 for v2); null unless "
        "approved."
    )


class ChangeRequestPage(BaseModel):
    change_requests: list[ChangeRequestResponse] = Field(description="Newest first.")
    next_cursor: str | None = Field(
        description="Send as `cursor` to read the next, older page. Null on the last page."
    )


class ChangeOperation(ItemChangeResponse):
    """One item's change, found by comparing stable ids, with the agent's reason for it."""

    rationale: str | None = Field(description="Why the analysis proposed it, in its words.")


class ImpactNote(BaseModel):
    item_id: ItemId
    note: str = Field(description="How the change affects this item, in the agent's words.")


class ScopeReversalResponse(BaseModel):
    """A required scope decision: the change asks for work earlier scope ruled out. Only an
    approver records reverse or keep on it."""

    decision_id: DecisionId = Field(description="The decision on the candidate version.")
    reverses: Literal["exclusion", "decision"]
    summary: str = Field(description="What would be taken back.")
    reversed_decision_id: DecisionId | None = Field(
        description="For an earlier decision, its id on the baseline."
    )


class RemovedExclusion(BaseModel):
    """An exclusion of the baseline the candidate takes back, if its scope decision is reversed."""

    summary: str
    evidence: list[EvidenceRef]


class ChangeSetResponse(BaseModel):
    id: ChangeSetId
    change_request_id: ChangeRequestId
    base_version_id: BacklogVersionId
    base_content_hash: str
    candidate_version_id: BacklogVersionId
    candidate_content_hash: str
    operations: list[ChangeOperation] = Field(
        description="Items in the candidate's order, then removed items. Items not listed are "
        "unchanged, with the same ids and content as in the baseline."
    )
    removed_exclusions: list[RemovedExclusion]
    scope_decisions: list[ScopeReversalResponse]
    open_decision_ids: list[DecisionId] = Field(
        description="Decisions the candidate adds that nobody has settled yet."
    )
    impacts: list[ImpactNote] = Field(description="Dependency notes on items the change affects.")

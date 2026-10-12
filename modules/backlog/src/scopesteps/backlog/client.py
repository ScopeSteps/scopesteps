from typing import Literal, NewType
from uuid import UUID

from pydantic import BaseModel, Field

from scopesteps.evidence.client import EvidenceRef

BacklogVersionId = NewType("BacklogVersionId", UUID)
ItemId = NewType("ItemId", UUID)
CriterionId = NewType("CriterionId", UUID)

ClaimOrigin = Literal["source", "human", "proposed"]


class AcceptanceCriterion(BaseModel):
    id: CriterionId
    text: str = Field(min_length=1)
    origin: ClaimOrigin
    evidence: list[EvidenceRef] = []


class BacklogItem(BaseModel):
    """An epic or story. `id` is stable across versions; edits never reuse it for new work."""

    id: ItemId
    kind: Literal["epic", "story"]
    parent_id: ItemId | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    criteria: list[AcceptanceCriterion] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    blockers: list[str] = []
    human_edited: bool = False

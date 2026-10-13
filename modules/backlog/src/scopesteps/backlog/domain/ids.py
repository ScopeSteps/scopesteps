from typing import NewType
from uuid import UUID

BacklogVersionId = NewType("BacklogVersionId", UUID)
ItemId = NewType("ItemId", UUID)
CriterionId = NewType("CriterionId", UUID)
DecisionId = NewType("DecisionId", UUID)

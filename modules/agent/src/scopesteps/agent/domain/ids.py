from typing import NewType
from uuid import UUID

RunId = NewType("RunId", UUID)
QuestionId = NewType("QuestionId", UUID)
StepId = NewType("StepId", UUID)
MessageId = NewType("MessageId", UUID)

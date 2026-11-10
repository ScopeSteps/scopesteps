from typing import NewType
from uuid import UUID

PublishId = NewType("PublishId", UUID)
OutboxEntryId = NewType("OutboxEntryId", UUID)

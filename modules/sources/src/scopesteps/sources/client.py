from typing import NewType
from uuid import UUID

SourceId = NewType("SourceId", UUID)
SourceVersionId = NewType("SourceVersionId", UUID)
SourceBlockId = NewType("SourceBlockId", UUID)

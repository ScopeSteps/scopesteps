"""draft progress on runs

Revision ID: a3c91d5e7b20
Revises: f47b1d0d577c
Create Date: 2026-11-06 10:00:00.000000

A draft written in steps (ADR 0028) keeps its finished steps between advances: the outline and
each epic's stories. It holds model output, so like the run's history it is never returned by the
API. Existing runs drafted in one call and have none.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c91d5e7b20"
down_revision: str | None = "f47b1d0d577c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("draft_progress", sa.JSON(), nullable=True))


def downgrade() -> None:
    # A run part-way through a stepwise draft loses its finished steps; advancing it again
    # writes them anew.
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("draft_progress")

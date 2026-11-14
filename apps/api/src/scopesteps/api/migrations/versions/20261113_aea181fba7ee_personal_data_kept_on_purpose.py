"""personal data kept on purpose

Revision ID: aea181fba7ee
Revises: 4938e363e739
Create Date: 2026-11-13 19:08:49.145036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aea181fba7ee"
down_revision: str | None = "4938e363e739"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_versions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kept_flags", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_versions", schema=None) as batch_op:
        batch_op.drop_column("kept_flags")

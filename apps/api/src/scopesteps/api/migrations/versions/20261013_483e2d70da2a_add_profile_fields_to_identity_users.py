"""add profile fields to identity users

Revision ID: 483e2d70da2a
Revises: 16900ed047fa
Create Date: 2026-10-13 19:39:29.776572
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "483e2d70da2a"
down_revision: str | None = "16900ed047fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("identity_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("job_title", sa.String(length=80), server_default="", nullable=False)
        )
        batch_op.add_column(
            sa.Column("about", sa.String(length=280), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("revision", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("identity_users", schema=None) as batch_op:
        batch_op.drop_column("revision")
        batch_op.drop_column("about")
        batch_op.drop_column("job_title")

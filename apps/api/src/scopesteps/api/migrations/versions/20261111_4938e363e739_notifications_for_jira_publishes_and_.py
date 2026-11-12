"""notifications for Jira publishes and tokens

Revision ID: 4938e363e739
Revises: 8c3530a0715d
Create Date: 2026-11-11 21:26:41.441992
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4938e363e739"
down_revision: str | None = "8c3530a0715d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notifications_email_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "email_on_jira_failure", sa.Boolean(), server_default=sa.true(), nullable=False
            )
        )

    with op.batch_alter_table("notifications_notifications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subject_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("version_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("details", sa.JSON(), nullable=True))
        batch_op.alter_column("thread_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("comment_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column(
            "kind",
            existing_type=sa.VARCHAR(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.create_index("ix_notifications_subject", ["subject_id", "kind"], unique=False)


def downgrade() -> None:
    # Jira notifications have no thread or comment, so they cannot survive the old columns.
    op.execute("DELETE FROM notifications_notifications WHERE thread_id IS NULL")
    with op.batch_alter_table("notifications_notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_subject")
        batch_op.alter_column(
            "kind",
            existing_type=sa.String(length=32),
            type_=sa.VARCHAR(length=16),
            existing_nullable=False,
        )
        batch_op.alter_column("comment_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("thread_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column("details")
        batch_op.drop_column("version_id")
        batch_op.drop_column("subject_id")

    with op.batch_alter_table("notifications_email_settings", schema=None) as batch_op:
        batch_op.drop_column("email_on_jira_failure")

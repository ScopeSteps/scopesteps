"""create audit events table

Revision ID: 06d64c2487e1
Revises: 2667749e8f15
Create Date: 2026-10-13 17:15:03.936636
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "06d64c2487e1"
down_revision: str | None = "2667749e8f15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "actor_kind",
            sa.Enum("user", "agent", name="actorkind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=200), nullable=True),
        # The event-type vocabulary grows in code; the column does not enumerate it.
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("subjects", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=200), nullable=False),
        sa.Column(
            "occurred_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(actor_kind = 'user' AND actor_user_id IS NOT NULL)"
            " OR (actor_kind <> 'user' AND actor_user_id IS NULL)",
            name=op.f("ck_audit_events_actor_matches_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["identity_users.id"],
            name=op.f("fk_audit_events_actor_user_id_identity_users"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects_projects.id"],
            name=op.f("fk_audit_events_project_id_projects_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_audit_events_project_feed", ["project_id", "occurred_at", "id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_project_feed")

    op.drop_table("audit_events")

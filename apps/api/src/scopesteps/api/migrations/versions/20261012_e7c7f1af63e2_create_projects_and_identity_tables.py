"""create projects and identity tables

Revision ID: e7c7f1af63e2
Revises:
Create Date: 2026-10-12 15:50:59.073711
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "e7c7f1af63e2"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_users")),
        sa.UniqueConstraint("email", name=op.f("uq_identity_users_email")),
    )
    op.create_table(
        "projects_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects_projects")),
    )
    op.create_table(
        "identity_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "viewer",
                "editor",
                "approver",
                "integration_admin",
                "workspace_admin",
                name="role",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects_projects.id"],
            name=op.f("fk_identity_memberships_project_id_projects_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_identity_memberships_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_memberships")),
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            "role",
            name=op.f("uq_identity_memberships_user_id_project_id_role"),
        ),
    )
    with op.batch_alter_table("identity_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_identity_memberships_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_identity_memberships_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("identity_memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_identity_memberships_user_id"))
        batch_op.drop_index(batch_op.f("ix_identity_memberships_project_id"))

    op.drop_table("identity_memberships")
    op.drop_table("projects_projects")
    op.drop_table("identity_users")

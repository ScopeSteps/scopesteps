"""add password hashes and sessions to identity

Revision ID: 16900ed047fa
Revises: d36243d6c366
Create Date: 2026-10-13 17:26:27.827429
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "16900ed047fa"
down_revision: str | None = "d36243d6c366"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_identity_sessions_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_identity_sessions_token_hash")),
    )
    with op.batch_alter_table("identity_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_identity_sessions_expires_at"), ["expires_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_identity_sessions_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("identity_users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("identity_users", schema=None) as batch_op:
        batch_op.drop_column("password_hash")

    with op.batch_alter_table("identity_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_identity_sessions_user_id"))
        batch_op.drop_index(batch_op.f("ix_identity_sessions_expires_at"))

    op.drop_table("identity_sessions")

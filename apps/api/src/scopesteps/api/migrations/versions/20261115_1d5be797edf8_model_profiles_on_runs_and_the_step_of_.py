"""model profiles on runs and the step of each step row

Revision ID: 1d5be797edf8
Revises: aea181fba7ee
Create Date: 2026-11-15 22:39:16.186354
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1d5be797edf8"
down_revision: str | None = "aea181fba7ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No backfill and no legacy profile: a database with runs from before profiles is reset
    # (`just reset-db`), since nothing is deployed (ADR 0032). The provider, model and fallback
    # reason a run pinned were keys of its `inputs` JSON, which new runs no longer write.
    with op.batch_alter_table("agent_run_steps", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "step",
                sa.Enum(
                    "explore",
                    "outline",
                    "epic_stories",
                    "change_explore",
                    "change",
                    "reply",
                    "suggest_tasks",
                    name="step",
                    native_enum=False,
                    length=32,
                ),
                nullable=True,
            )
        )

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("model_profile_id", sa.String(length=64), nullable=False))
        batch_op.add_column(sa.Column("model_profile_hash", sa.String(length=64), nullable=False))
        batch_op.add_column(sa.Column("model_bindings", sa.JSON(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_column("model_bindings")
        batch_op.drop_column("model_profile_hash")
        batch_op.drop_column("model_profile_id")

    with op.batch_alter_table("agent_run_steps", schema=None) as batch_op:
        batch_op.drop_column("step")

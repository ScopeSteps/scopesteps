"""number sources and allow removal

Revision ID: 520f3297f00d
Revises: fc95fb67afbc
Create Date: 2026-10-14 12:45:17.621789
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "520f3297f00d"
down_revision: str | None = "fc95fb67afbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


sources = sa.table(
    "sources_sources",
    sa.column("id", sa.Uuid()),
    sa.column("project_id", sa.Uuid()),
    sa.column("kind", sa.String()),
    sa.column("number", sa.Integer()),
    sa.column("created_at", sa.DateTime()),
)


def upgrade() -> None:
    with op.batch_alter_table("sources_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "removed_at",
                scopesteps.infrastructure.database.UtcDateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("removed_by", sa.Uuid(), nullable=True))
        batch_op.drop_constraint(batch_op.f("uq_sources_sources_project_id_kind"), type_="unique")

    # Existing sources are numbered per project in the order they were created.
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(sources.c.id, sources.c.project_id).order_by(
            sources.c.project_id, sources.c.created_at, sources.c.id
        )
    )
    numbers: dict[object, int] = {}
    for source_id, project_id in rows.all():
        numbers[project_id] = numbers.get(project_id, 0) + 1
        connection.execute(
            sa.update(sources).where(sources.c.id == source_id).values(number=numbers[project_id])
        )

    with op.batch_alter_table("sources_sources", schema=None) as batch_op:
        batch_op.alter_column("number", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            batch_op.f("uq_sources_sources_project_id_number"), ["project_id", "number"]
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_sources_sources_removed_by_identity_users"),
            "identity_users",
            ["removed_by"],
            ["id"],
        )


def downgrade() -> None:
    # The earlier schema allowed one source per kind and no removal: removed sources become
    # current again.
    duplicated = op.get_bind().execute(
        sa.select(sources.c.project_id, sources.c.kind)
        .group_by(sources.c.project_id, sources.c.kind)
        .having(sa.func.count() > 1)
        .limit(1)
    )
    if duplicated.first() is not None:
        raise RuntimeError("A project has more than one source of a kind; cannot downgrade")
    with op.batch_alter_table("sources_sources", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_sources_sources_removed_by_identity_users"), type_="foreignkey"
        )
        batch_op.drop_constraint(batch_op.f("uq_sources_sources_project_id_number"), type_="unique")
        batch_op.create_unique_constraint(
            batch_op.f("uq_sources_sources_project_id_kind"), ["project_id", "kind"]
        )
        batch_op.drop_column("removed_by")
        batch_op.drop_column("removed_at")
        batch_op.drop_column("number")

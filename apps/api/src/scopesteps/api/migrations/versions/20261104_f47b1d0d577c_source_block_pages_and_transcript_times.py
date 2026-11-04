"""source block pages and transcript times

Revision ID: f47b1d0d577c
Revises: c7e6e367bbe0
Create Date: 2026-11-04 17:33:39.739579

Word, PDF and WebVTT files can be uploaded and are converted to text (ADR 0025). A block keeps
the PDF page it is on and a transcript block the time and speaker it starts with; existing
blocks have none. The media type column grows to hold the Word type's 71 characters.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f47b1d0d577c"
down_revision: str | None = "c7e6e367bbe0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen here: a migration must not change when the app's code does.
_TEXT_TYPES = ("text/plain", "text/markdown")


def upgrade() -> None:
    with op.batch_alter_table("sources_blocks") as batch_op:
        batch_op.add_column(sa.Column("page", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("start_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("speaker", sa.String(length=60), nullable=True))

    with op.batch_alter_table("sources_versions") as batch_op:
        batch_op.alter_column(
            "media_type",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Before this revision only text could be stored, so a converted file has nowhere to go.
    # Deleting it would break the citations that point at it; stop instead.
    converted = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM sources_versions WHERE media_type NOT IN :types"
            ).bindparams(sa.bindparam("types", expanding=True)),
            {"types": list(_TEXT_TYPES)},
        )
        .scalar_one()
    )
    if converted:
        raise RuntimeError(
            f"{converted} source version(s) came from Word, PDF or WebVTT files, which the "
            "earlier schema cannot hold. Remove them before downgrading."
        )

    with op.batch_alter_table("sources_versions") as batch_op:
        batch_op.alter_column(
            "media_type",
            existing_type=sa.String(length=128),
            type_=sa.String(length=32),
            existing_nullable=False,
        )

    with op.batch_alter_table("sources_blocks") as batch_op:
        batch_op.drop_column("speaker")
        batch_op.drop_column("start_ms")
        batch_op.drop_column("page")

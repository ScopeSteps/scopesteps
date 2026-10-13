"""create sources tables

Revision ID: 46ff3a9d289e
Revises: e7c7f1af63e2
Create Date: 2026-10-12 19:51:45.332043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "46ff3a9d289e"
down_revision: str | None = "e7c7f1af63e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("brief", "transcript", name="sourcekind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects_projects.id"],
            name=op.f("fk_sources_sources_project_id_projects_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources_sources")),
        sa.UniqueConstraint("project_id", "kind", name=op.f("uq_sources_sources_project_id_kind")),
    )
    op.create_table(
        "sources_upload_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_version_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["identity_users.id"],
            name=op.f("fk_sources_upload_receipts_actor_id_identity_users"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects_projects.id"],
            name=op.f("fk_sources_upload_receipts_project_id_projects_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources_upload_receipts")),
        sa.UniqueConstraint(
            "project_id",
            "actor_id",
            "idempotency_key",
            name=op.f("uq_sources_upload_receipts_project_id_actor_id_idempotency_key"),
        ),
    )
    op.create_table(
        "sources_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("text/plain", "text/markdown", name="mediatype", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources_sources.id"],
            name=op.f("fk_sources_versions_source_id_sources_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["identity_users.id"],
            name=op.f("fk_sources_versions_uploaded_by_identity_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources_versions")),
        sa.UniqueConstraint(
            "source_id", "version", name=op.f("uq_sources_versions_source_id_version")
        ),
    )
    op.create_table(
        "sources_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["sources_versions.id"],
            name=op.f("fk_sources_blocks_source_version_id_sources_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources_blocks")),
        sa.UniqueConstraint(
            "source_version_id", "ordinal", name=op.f("uq_sources_blocks_source_version_id_ordinal")
        ),
    )


def downgrade() -> None:
    op.drop_table("sources_blocks")
    op.drop_table("sources_versions")
    op.drop_table("sources_upload_receipts")
    op.drop_table("sources_sources")

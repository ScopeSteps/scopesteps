"""mentions followers notifications and change request links

Revision ID: b217cec4e1c2
Revises: 922fbea20ea3
Create Date: 2026-10-31 16:32:41.919905
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import scopesteps.infrastructure.database

revision: str = "b217cec4e1c2"
down_revision: str | None = "922fbea20ea3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications_email_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_on_mention", sa.Boolean(), nullable=False),
        sa.Column("email_on_reply", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_notifications_email_settings_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_notifications_email_settings")),
    )
    op.create_table(
        "notifications_email_windows",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column(
            "last_sent_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_notifications_email_windows_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "thread_id", name=op.f("pk_notifications_email_windows")
        ),
    )
    with op.batch_alter_table("notifications_email_windows", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_email_windows_last_sent_at"),
            ["last_sent_at"],
            unique=False,
        )

    op.create_table(
        "notifications_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("comment_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "read_at", scopesteps.infrastructure.database.UtcDateTime(timezone=True), nullable=True
        ),
        sa.Column("email_waiting", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["identity_users.id"],
            name=op.f("fk_notifications_notifications_actor_id_identity_users"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects_projects.id"],
            name=op.f("fk_notifications_notifications_project_id_projects_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_notifications_notifications_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications_notifications")),
    )
    with op.batch_alter_table("notifications_notifications", schema=None) as batch_op:
        batch_op.create_index("ix_notifications_comment", ["comment_id", "kind"], unique=False)
        batch_op.create_index("ix_notifications_created_at", ["created_at"], unique=False)
        batch_op.create_index(
            "ix_notifications_email_waiting", ["email_waiting", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_notifications_list", ["user_id", "created_at", "id"], unique=False
        )

    op.create_table(
        "discussions_thread_followers",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("muted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["discussions_threads.id"],
            name=op.f("fk_discussions_thread_followers_thread_id_discussions_threads"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_users.id"],
            name=op.f("fk_discussions_thread_followers_user_id_identity_users"),
        ),
        sa.PrimaryKeyConstraint(
            "thread_id", "user_id", name=op.f("pk_discussions_thread_followers")
        ),
    )
    with op.batch_alter_table("discussions_thread_followers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_discussions_thread_followers_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "discussions_change_requests",
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            scopesteps.infrastructure.database.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_control_change_requests.id"],
            name="fk_discussions_change_requests_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity_users.id"],
            name=op.f("fk_discussions_change_requests_created_by_identity_users"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["discussions_threads.id"],
            name=op.f("fk_discussions_change_requests_thread_id_discussions_threads"),
        ),
        sa.PrimaryKeyConstraint("change_request_id", name=op.f("pk_discussions_change_requests")),
    )
    with op.batch_alter_table("discussions_change_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_discussions_change_requests_thread_id"), ["thread_id"], unique=False
        )

    # Whoever already commented follows their threads, as they would have from the start.
    comments = sa.table(
        "discussions_comments", sa.column("thread_id", sa.Uuid()), sa.column("author_id", sa.Uuid())
    )
    followers = sa.table(
        "discussions_thread_followers",
        sa.column("thread_id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("muted", sa.Boolean()),
    )
    op.execute(
        followers.insert().from_select(
            ["thread_id", "user_id", "muted"],
            sa.select(comments.c.thread_id, comments.c.author_id, sa.false()).distinct(),
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("discussions_change_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_discussions_change_requests_thread_id"))

    op.drop_table("discussions_change_requests")
    with op.batch_alter_table("discussions_thread_followers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_discussions_thread_followers_user_id"))

    op.drop_table("discussions_thread_followers")
    with op.batch_alter_table("notifications_notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_list")
        batch_op.drop_index("ix_notifications_email_waiting")
        batch_op.drop_index("ix_notifications_created_at")
        batch_op.drop_index("ix_notifications_comment")

    op.drop_table("notifications_notifications")
    with op.batch_alter_table("notifications_email_windows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_email_windows_last_sent_at"))

    op.drop_table("notifications_email_windows")
    op.drop_table("notifications_email_settings")

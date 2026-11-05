"""one role per project member

Revision ID: c7e6e367bbe0
Revises: b217cec4e1c2
Create Date: 2026-11-04 15:02:20.370222

Each member now holds one role per project, and each role includes the ones below it
(ADR 0024). Upgrading keeps every member's highest role, so nobody loses access: Editor and
Approver together become Approver. Invitations keep their highest role the same way.
Downgrading gives back the roles the old rules needed for the same access: an Approver gets
Editor too.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "c7e6e367bbe0"
down_revision: str | None = "b217cec4e1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lowest first. Frozen here: a migration must not change when the app's code does.
_LADDER = ("viewer", "editor", "approver")
# What each role meant under the old rules, where roles combined and none implied another.
_OLD_ROLES = {"viewer": ["viewer"], "editor": ["editor"], "approver": ["editor", "approver"]}

_ROLE = sa.Enum(
    "viewer",
    "editor",
    "approver",
    "integration_admin",
    "workspace_admin",
    name="role",
    native_enum=False,
    length=32,
)

_memberships = sa.table(
    "identity_memberships",
    sa.column("id", sa.Uuid()),
    sa.column("user_id", sa.Uuid()),
    sa.column("project_id", sa.Uuid()),
    sa.column("role", sa.String()),
    sa.column("granted_at", sa.DateTime(timezone=True)),
)
_invitations = sa.table(
    "identity_invitations",
    sa.column("id", sa.Uuid()),
    sa.column("roles", sa.JSON()),
    sa.column("role", sa.String()),
)


def _rank(role: str) -> int:
    # Admin roles were never granted per project; ranked below everything so any project role
    # wins over them.
    return _LADDER.index(role) if role in _LADDER else -1


def _highest(roles: Sequence[str]) -> str:
    return max(roles, key=_rank) if roles else "viewer"


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("identity_invitations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role", _ROLE, nullable=True))
    for invitation_id, roles in bind.execute(sa.select(_invitations.c.id, _invitations.c.roles)):
        bind.execute(
            sa.update(_invitations)
            .where(_invitations.c.id == invitation_id)
            .values(role=_highest(list(roles or [])))
        )
    with op.batch_alter_table("identity_invitations", schema=None) as batch_op:
        batch_op.alter_column("role", existing_type=_ROLE, nullable=False)
        batch_op.drop_column("roles")

    kept: dict[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, str]] = {}
    extra: list[uuid.UUID] = []
    rows = bind.execute(
        sa.select(
            _memberships.c.id,
            _memberships.c.user_id,
            _memberships.c.project_id,
            _memberships.c.role,
        )
    )
    for membership_id, user_id, project_id, role in rows:
        key = (user_id, project_id)
        held = kept.get(key)
        if held is None or _rank(role) > _rank(held[1]):
            if held is not None:
                extra.append(held[0])
            kept[key] = (membership_id, role)
        else:
            extra.append(membership_id)
    if extra:
        bind.execute(sa.delete(_memberships).where(_memberships.c.id.in_(extra)))

    with op.batch_alter_table("identity_memberships", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("uq_identity_memberships_user_id_project_id_role"), type_="unique"
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_identity_memberships_user_id_project_id"), ["user_id", "project_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("identity_memberships", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("uq_identity_memberships_user_id_project_id"), type_="unique"
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_identity_memberships_user_id_project_id_role"),
            ["user_id", "project_id", "role"],
        )
    rows = bind.execute(
        sa.select(
            _memberships.c.user_id,
            _memberships.c.project_id,
            _memberships.c.role,
            _memberships.c.granted_at,
        )
    ).all()
    for user_id, project_id, role, granted_at in rows:
        for old in _OLD_ROLES.get(role, [role]):
            if old != role:
                bind.execute(
                    sa.insert(_memberships).values(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        project_id=project_id,
                        role=old,
                        granted_at=granted_at or datetime.now(UTC),
                    )
                )

    with op.batch_alter_table("identity_invitations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("roles", sa.JSON(), nullable=True))
    for invitation_id, role in bind.execute(sa.select(_invitations.c.id, _invitations.c.role)):
        bind.execute(
            sa.update(_invitations)
            .where(_invitations.c.id == invitation_id)
            .values(roles=_OLD_ROLES.get(role, [role]))
        )
    with op.batch_alter_table("identity_invitations", schema=None) as batch_op:
        batch_op.alter_column("roles", existing_type=sa.JSON(), nullable=False)
        batch_op.drop_column("role")

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from scopesteps.api.migrations import alembic_config, upgrade_to_head
from scopesteps.api.seed import LOCAL_REVIEWER_ID, seed
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

ClientFactory = Callable[..., TestClient]


def test_seeded_data_survives_an_application_restart(
    seeded_database_url: str, make_client: ClientFactory
) -> None:
    first = make_client(seeded_database_url).get("/api/v1/me").json()
    restarted: TestClient = make_client(seeded_database_url)

    second = restarted.get("/api/v1/me").json()

    assert first == second
    assert second["id"] == str(LOCAL_REVIEWER_ID)


def test_seed_is_idempotent(migrated_database_url: str) -> None:
    engine = create_database_engine(migrated_database_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        first_run_created = seed(session)
    with session_factory() as session:
        second_run_created = seed(session)
    engine.dispose()

    assert first_run_created is True
    assert second_run_created is False


def test_migrations_downgrade_and_upgrade_cleanly(database_url: str) -> None:
    upgrade_to_head(database_url)
    command.downgrade(alembic_config(database_url), "base")
    engine = create_database_engine(database_url)
    tables_after_downgrade = set(inspect(engine).get_table_names())

    upgrade_to_head(database_url)
    tables_after_upgrade = set(inspect(engine).get_table_names())
    engine.dispose()

    assert tables_after_downgrade == {"alembic_version"}
    assert {
        "projects_projects",
        "identity_users",
        "identity_memberships",
        "identity_sessions",
    } <= tables_after_upgrade


def test_migrations_rebuild_referenced_sqlite_tables(database_url: str, tmp_path: Path) -> None:
    # 520f3297f00d rebuilds sources_sources, which sources_versions references.
    command.upgrade(alembic_config(database_url), "fc95fb67afbc")
    with sqlite3.connect(tmp_path / "scopesteps.db") as connection:
        connection.executescript(
            """
            INSERT INTO identity_users (id, email, display_name, created_at)
            VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'reviewer@example.test', 'Reviewer', '2026-01-01 00:00:00');
            INSERT INTO projects_projects (id, name, created_at)
            VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'Demo', '2026-01-01 00:00:00');
            INSERT INTO sources_sources (id, project_id, kind, created_at)
            VALUES ('cccccccccccccccccccccccccccccccc', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'transcript', '2026-01-01 00:00:00');
            INSERT INTO sources_versions (id, source_id, version, filename, media_type,
                checksum_sha256, byte_size, word_count, block_count, text, uploaded_by, created_at)
            VALUES ('dddddddddddddddddddddddddddddddd', 'cccccccccccccccccccccccccccccccc', 1, 'notes.txt', 'text/plain', '', 0, 0, 0, '', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '2026-01-01 00:00:00');
            """
        )
    connection.close()

    upgrade_to_head(database_url)

    with sqlite3.connect(tmp_path / "scopesteps.db") as connection:
        numbers = connection.execute("SELECT number FROM sources_sources").fetchall()
    connection.close()
    assert numbers == [(1,)]


def test_one_role_migration_keeps_each_members_highest_role_both_ways(database_url: str) -> None:
    before, after = "b217cec4e1c2", "c7e6e367bbe0"
    command.upgrade(alembic_config(database_url), before)
    engine = create_database_engine(database_url)
    project, inviter = uuid4(), uuid4()
    owner, editor, viewer = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO projects_projects (id, name, created_at) VALUES (:id, 'Demo', :at)"),
            {"id": project.hex, "at": "2026-01-01 00:00:00"},
        )
        for user in (inviter, owner, editor, viewer):
            connection.execute(
                text(
                    "INSERT INTO identity_users (id, email, display_name, created_at) "
                    "VALUES (:id, :email, 'Someone', :at)"
                ),
                {"id": user.hex, "email": f"{user.hex}@example.test", "at": "2026-01-01 00:00:00"},
            )
        held = {owner: ("editor", "approver"), editor: ("editor",), viewer: ("viewer",)}
        for user, roles in held.items():
            for role in roles:
                connection.execute(
                    text(
                        "INSERT INTO identity_memberships (id, user_id, project_id, role, "
                        "granted_at) VALUES (:id, :user, :project, :role, :at)"
                    ),
                    {
                        "id": uuid4().hex,
                        "user": user.hex,
                        "project": project.hex,
                        "role": role,
                        "at": "2026-01-01 00:00:00",
                    },
                )
        connection.execute(
            text(
                "INSERT INTO identity_invitations (id, project_id, email, roles, invited_by, "
                "token_hash, expires_at, created_at) VALUES (:id, :project, 'new@example.test', "
                ":roles, :by, :hash, :at, :at)"
            ),
            {
                "id": uuid4().hex,
                "project": project.hex,
                "roles": '["viewer", "editor"]',
                "by": inviter.hex,
                "hash": "0" * 64,
                "at": "2026-01-01 00:00:00",
            },
        )

    def roles_now() -> dict[str, list[str]]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT user_id, role FROM identity_memberships"))
            found: dict[str, list[str]] = {}
            for user_id, role in rows:
                found.setdefault(str(user_id).replace("-", ""), []).append(role)
        return {user: sorted(held) for user, held in found.items()}

    command.upgrade(alembic_config(database_url), after)
    upgraded = roles_now()
    with engine.connect() as connection:
        invited_as = connection.execute(text("SELECT role FROM identity_invitations")).scalar()
    command.downgrade(alembic_config(database_url), before)
    downgraded = roles_now()
    with engine.connect() as connection:
        invited_as_before = connection.execute(
            text("SELECT roles FROM identity_invitations")
        ).scalar()
    engine.dispose()

    assert upgraded == {owner.hex: ["approver"], editor.hex: ["editor"], viewer.hex: ["viewer"]}
    assert invited_as == "editor"
    assert downgraded == {
        owner.hex: ["approver", "editor"],
        editor.hex: ["editor"],
        viewer.hex: ["viewer"],
    }
    assert json.loads(str(invited_as_before)) == ["editor"]

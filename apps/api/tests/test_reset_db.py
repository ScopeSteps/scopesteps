import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from scopesteps.api import reset_db
from scopesteps.api.migrations import upgrade_to_head
from scopesteps.api.seed import seed
from scopesteps.api.settings import Settings
from scopesteps.infrastructure.database import create_database_engine, create_session_factory

PROJECT_ID = "019a3a5e-0000-7000-8000-000000000001"


def test_a_reset_empties_a_database_that_no_downgrade_could_and_it_migrates_again(
    client: TestClient, seeded_database_url: str
) -> None:
    # Two briefs in one project: the data the sources downgrade refuses to drop.
    for number in (1, 2):
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/sources",
            files={"brief": (f"brief-{number}.md", f"Brief number {number}.".encode())},
            headers={"Idempotency-Key": f"reset-upload-{number}"},
        )
        assert response.status_code == 201, response.text
    engine = create_database_engine(seeded_database_url)

    dropped = reset_db.drop_all_tables(engine)

    assert dropped > 0
    assert inspect(engine).get_table_names() == []
    upgrade_to_head(seeded_database_url)
    with create_session_factory(engine)() as session:
        assert seed(session), "a reset database seeds from scratch"
    engine.dispose()


def test_a_reset_is_refused_outside_a_local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_construct(app_env="demo", database_url="sqlite:///unused.db")
    monkeypatch.setattr(reset_db, "get_settings", lambda: settings)
    dropped: list[object] = []
    monkeypatch.setattr(reset_db, "drop_all_tables", dropped.append)

    with pytest.raises(SystemExit, match="APP_ENV=demo"):
        reset_db.main()

    assert dropped == []

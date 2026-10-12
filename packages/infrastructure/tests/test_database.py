from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from scopesteps.infrastructure.database import (
    UtcDateTime,
    create_database_engine,
    create_session_factory,
)


class _TestBase(DeclarativeBase):
    pass


class _Event(_TestBase):
    __tablename__ = "test_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime)


def test_sqlite_engine_creates_parent_directory_and_enables_foreign_keys(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/nested/app.db")

    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert (tmp_path / "nested" / "app.db").exists()
    assert foreign_keys == 1


def test_utc_datetime_round_trips_as_aware_utc(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/app.db")
    _TestBase.metadata.create_all(engine)
    plus_two = timezone(timedelta(hours=2))
    stored = datetime(2026, 10, 12, 14, 0, tzinfo=plus_two)

    with create_session_factory(engine)() as session:
        session.add(_Event(id=1, occurred_at=stored))
        session.commit()
        loaded = session.scalars(select(_Event.occurred_at)).one()

    assert loaded == stored
    assert loaded.tzinfo == UTC


def test_utc_datetime_rejects_naive_values(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path}/app.db")
    _TestBase.metadata.create_all(engine)

    with create_session_factory(engine)() as session:
        session.add(_Event(id=1, occurred_at=datetime(2026, 10, 12, 14, 0)))  # noqa: DTZ001
        with pytest.raises(Exception, match="Naive datetimes"):
            session.commit()

"""Empties the local database so `just reset-db` can migrate and seed it from scratch.

Every table is dropped, Alembic's version table and any leftover `_alembic_tmp_*` table included,
instead of downgrading: downgrades are written to keep data safe and refuse to run once data
would not fit the older schema, while a reset throws the data away anyway.
"""

import sys

from sqlalchemy import Engine, MetaData, make_url, text

from scopesteps.api.settings import get_settings
from scopesteps.infrastructure.database import create_database_engine


def drop_all_tables(engine: Engine) -> int:
    """Drop every table in the database and return how many there were."""
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            # Off before the drops begin (SQLite ignores the pragma inside a transaction), so a
            # cycle between tables or a stray leftover table cannot block them.
            connection.execute(text("PRAGMA foreign_keys = OFF"))
            connection.commit()
        metadata.drop_all(connection)
        connection.commit()
    return len(metadata.tables)


def main() -> None:
    settings = get_settings()
    if not settings.is_local_environment:
        sys.exit(f"Refusing to reset a database with APP_ENV={settings.app_env}.")
    url = make_url(settings.database_url)
    engine = create_database_engine(settings.database_url)
    try:
        dropped = drop_all_tables(engine)
    finally:
        engine.dispose()
    target = url.render_as_string(hide_password=True)
    sys.stdout.write(f"Dropped {dropped} tables from {target}.\n")


if __name__ == "__main__":
    main()

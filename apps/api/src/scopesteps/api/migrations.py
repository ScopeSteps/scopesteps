from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

SCRIPT_LOCATION = "scopesteps.api:migrations"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def schema_is_current(engine: Engine) -> bool:
    expected = set(ScriptDirectory.from_config(alembic_config()).get_heads())
    with engine.connect() as connection:
        applied = set(MigrationContext.configure(connection).get_current_heads())
    return applied == expected

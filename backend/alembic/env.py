"""Alembic environment.

The async driver suffix is stripped so migrations run against a sync
engine; the URL is taken from app settings unless overridden by alembic.ini
or -x url=. Metadata comes from the app models (register them by importing
app.models).
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
import app.models  # noqa: F401  (register all mappers)

config = context.config

# Honour an explicitly-configured URL (tests, tooling); otherwise derive
# from app settings, stripping the async driver suffix.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option(
        "sqlalchemy.url",
        get_settings().DATABASE_URL.replace("+aiosqlite", "").replace("+asyncpg", ""),
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

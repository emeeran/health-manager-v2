"""Async database engine and session management.

SQLite pragmas: WAL for concurrent readers, generous busy_timeout.
foreign_keys is deliberately NOT enabled (matches upstream behaviour).
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite"):
        return create_async_engine(url, connect_args={"timeout": 30})
    return create_async_engine(url, pool_pre_ping=True, pool_recycle=1800)


settings = get_settings()
engine = _make_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    """Run `alembic upgrade head` (SQLite boot path).

    The baseline is a squashed create_all, so fresh databases are fully
    created and stamped; existing ones receive incremental migrations.
    Postgres keeps external migration discipline.
    """
    import asyncio

    from alembic import command
    from alembic.config import Config

    import app.models  # noqa: F401, PLC0415  (register mappers)

    if not settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # pragma: no cover
        return

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[2] / "alembic"),
    )
    url = settings.DATABASE_URL.replace("+aiosqlite", "")
    cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

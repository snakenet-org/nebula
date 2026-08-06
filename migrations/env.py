#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Alembic migration environment for the Nebula database.
@ai-context: Wires Alembic to the application's SQLAlchemy metadata (nebula.database.Base, with all
  ORM tables imported from nebula.models.tables) and reuses nebula.config.settings for the async
  asyncpg connection URL — same source of truth the app itself connects with. Used by
  `alembic revision --autogenerate` and `alembic upgrade head` (run from entrypoint.sh on start).
  `_ensure_database_exists()` runs first, connecting to the `postgres` maintenance database to
  `CREATE DATABASE` settings.pg_db if it's not there yet — the shipped Docker image's entrypoint.sh
  already handles this itself for its embedded Postgres (a first-boot `createdb` before `alembic
  upgrade head`), but `alembic upgrade head` run directly against an external/local Postgres (see
  docs/deployment.md's "Building from source" section) has no equivalent, so it always failed on a
  brand-new server with no NEBULA_POSTGRES_DB database yet — this makes alembic self-sufficient
  either way.
@ai-rules:
  - Never expose raw DB credentials in logs or API responses.
  - Maintain 100% type-hinting coverage.
@dependencies: alembic, sqlalchemy[asyncio], asyncpg, python-dotenv
@version: 1.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import asyncio
from logging.config import fileConfig

import asyncpg
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Import the metadata + all ORM tables so autogenerate can see the full schema.
import nebula.models.tables  # noqa: F401  (registers every table on Base.metadata)
from nebula.config import settings
from nebula.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


async def _ensure_database_exists() -> None:
    """Create settings.pg_db on the target Postgres server if it doesn't exist yet.

    Connects to the server's built-in `postgres` maintenance database (always present, never the
    target database itself) rather than settings.database_url, since a fresh server has nothing
    else to connect to before the target database is created.
    """
    conn = await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        user=settings.pg_user,
        password=settings.pg_password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", settings.pg_db
        )
        if not exists:
            # CREATE DATABASE can't be parameterized or run inside a transaction; pg_db is
            # operator-supplied server config (NEBULA_POSTGRES_DB), not untrusted user input.
            await conn.execute(f'CREATE DATABASE "{settings.pg_db}"')
    finally:
        await conn.close()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB-API connection)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode against an async engine."""
    await _ensure_database_exists()
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

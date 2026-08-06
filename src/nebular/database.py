#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Shared SQLAlchemy asyncio engine, session factory, and FastAPI session dependency.
@ai-context: Configures a single async PostgreSQL engine using the asyncpg driver, reading
  settings.database_url (nebular.config) rather than os.getenv directly. Exports get_session() as a
  FastAPI Depends() provider used by all DB-aware routers, async_session_factory for non-request code
  (startup seeding, the scheduler-less startup canary check in main.py), and Base for ORM model
  declarations.
@ai-rules:
  - Never expose raw DB credentials in logs or API responses.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio], asyncpg
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from nebular.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped async session."""
    async with async_session_factory() as session:
        yield session

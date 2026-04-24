"""Database session configuration."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings

# Render provides postgres:// URLs, but asyncpg requires postgresql+asyncpg://
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Free tier DBs have limited connections — use smaller pool in production
_pool_size = 5 if settings.APP_ENV == "production" else settings.DATABASE_POOL_SIZE
_max_overflow = 3 if settings.APP_ENV == "production" else settings.DATABASE_MAX_OVERFLOW

def _build_engine(*, use_null_pool: bool = False):
    kwargs = {
        "echo": settings.APP_DEBUG,
    }
    if use_null_pool:
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = _pool_size
        kwargs["max_overflow"] = _max_overflow

    return create_async_engine(db_url, **kwargs)


def _build_session_factory(bind):
    return async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# Create async engine and session factory
engine = _build_engine()
AsyncSessionLocal = _build_session_factory(engine)


def reset_engine_for_worker():
    """Install a fresh engine and session factory.

    Celery worker processes run each task in a new event loop via run_async().
    asyncpg's internal futures are bound to the loop that created them, so the
    shared module-level engine cannot be reused across loops (raises
    "Future attached to a different loop"). Call this at the start of each
    task to give the upcoming loop a clean engine. Use a null pool so worker
    tasks do not accidentally reuse asyncpg connections across loop lifetimes.
    """
    global engine, AsyncSessionLocal
    engine = _build_engine(use_null_pool=True)
    AsyncSessionLocal = _build_session_factory(engine)


async def get_db():
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

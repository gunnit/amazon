"""Database session configuration."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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

# Create async engine
engine = create_async_engine(
    db_url,
    echo=settings.APP_DEBUG,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


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

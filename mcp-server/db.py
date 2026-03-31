import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Load .env from backend
_backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env)

DATABASE_URL = os.getenv("MCP_DATABASE_URL") or os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    try:
        from config import get_active_database_url
        DATABASE_URL = get_active_database_url() or ""
    except Exception:
        pass
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Create backend/.env, set MCP_DATABASE_URL, or configure a profile via inthezon-cli.")

engine = create_async_engine(DATABASE_URL, pool_size=3, max_overflow=2, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

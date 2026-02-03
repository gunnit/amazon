# Database modules
from app.db.base import Base

__all__ = ["Base"]


def get_db():
    """Lazy import to avoid async engine issues during migrations."""
    from app.db.session import get_db as _get_db
    return _get_db()


def get_engine():
    """Lazy import to avoid async engine issues during migrations."""
    from app.db.session import engine
    return engine


def get_async_session_local():
    """Lazy import to avoid async engine issues during migrations."""
    from app.db.session import AsyncSessionLocal
    return AsyncSessionLocal

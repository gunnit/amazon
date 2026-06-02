"""API dependencies."""
import logging
import time
from typing import Optional, Annotated
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db.session import get_db
from app.core.security import decode_token
from app.models.user import User, Organization, OrganizationMember

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Lazily-initialized sync Redis client shared by the rate limiter and the
# token blacklist. None means "unavailable"; callers must degrade gracefully.
_redis_client = None
_redis_init_done = False


def _get_redis():
    """Return a shared Redis client, or None if it cannot be reached.

    Connection errors are swallowed and cached so we don't retry on every
    request when Redis is down — the dependent features degrade open.
    """
    global _redis_client, _redis_init_done
    if _redis_init_done:
        return _redis_client
    _redis_init_done = True
    if not settings.REDIS_URL:
        return None
    try:
        import redis

        client = redis.from_url(
            settings.REDIS_URL,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
        client.ping()
        _redis_client = client
    except Exception:
        logger.warning("Redis unavailable; rate limiting and token revocation disabled")
        _redis_client = None
    return _redis_client


def is_token_revoked(jti: str) -> bool:
    """Check the JTI blacklist. Degrades open if Redis is unavailable."""
    if not jti:
        return False
    client = _get_redis()
    if client is None:
        return False
    try:
        return bool(client.exists(f"jwt:revoked:{jti}"))
    except Exception:
        logger.warning("Token revocation check failed; allowing request", exc_info=True)
        return False


def revoke_token(jti: str, exp: Optional[int]) -> bool:
    """Add a JTI to the blacklist until the token would have expired.

    Returns True if the revocation was persisted. Fails closed: callers
    (logout) should surface an error if this returns False.
    """
    if not jti:
        return False
    client = _get_redis()
    if client is None:
        return False
    ttl = 3600
    if exp:
        ttl = max(1, int(exp - time.time()))
    try:
        client.set(f"jwt:revoked:{jti}", "1", ex=ttl)
        return True
    except Exception:
        logger.warning("Failed to revoke token", exc_info=True)
        return False


class RateLimiter:
    """Fixed-window per-client rate limiter backed by Redis.

    Used as a FastAPI dependency on sensitive endpoints. If Redis is
    unavailable the limiter allows the request rather than locking users out.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60, scope: str = "default"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.scope = scope

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown"
        )
        return f"ratelimit:{self.scope}:{ip}"

    async def __call__(self, request: Request) -> None:
        client = _get_redis()
        if client is None:
            return
        key = self._client_key(request)
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, self.window_seconds)
        except Exception:
            logger.warning("Rate limit check failed; allowing request", exc_info=True)
            return
        if count > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user."""
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_revoked(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user if they are a superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_user_organization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get the user's organization."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(OrganizationMember.user_id == current_user.id)
    )
    organization = result.scalar_one_or_none()

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of any organization",
        )

    return organization


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]
CurrentOrganization = Annotated[Organization, Depends(get_user_organization)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

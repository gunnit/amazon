"""Alembic migration environment."""
from logging.config import fileConfig

from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection

from alembic import context

# Import models and base
from app.db.base import Base
from app.models import *  # noqa
from app.config import settings

# Alembic Config object
config = context.config

# Set sqlalchemy.url from settings - use sync driver for migrations
# Handle Render's postgres:// URLs and local postgresql+asyncpg:// URLs
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    sync_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://"):
    sync_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif "asyncpg" in db_url:
    sync_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
else:
    sync_url = db_url
config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model's MetaData for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

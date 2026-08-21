from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models_registry  # noqa: F401  — populates Base.metadata
from app.core.models_base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """마이그레이션이 붙을 PostgreSQL 주소.

    `normalize_database_url` 을 지나게 해서 앱과 **같은 드라이버**로 붙는다. 여기만
    psycopg2 로 붙으면 타입 어댑터가 달라져, 마이그레이션에서는 되는데 런타임에서는
    안 되는 자리가 생긴다.
    """
    from app.core.db import normalize_database_url

    url = os.environ.get("DATABASE_URL")
    if not url:
        from app.core.config import Settings

        url = Settings().database_url
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Alembic environment: uses the application's settings and metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers all tables on Base.metadata)
from app.db.base import Base, include_name
from app.db.session import build_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, **kwargs: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        include_name=include_name,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=get_settings().sqlalchemy_url().render_as_string(hide_password=True),
               literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests pass an open connection via config.attributes to target a separate database.
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = build_engine(get_settings())
    try:
        with engine.connect() as conn:
            _configure(conn)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

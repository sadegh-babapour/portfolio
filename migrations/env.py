from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app import runtime_db, runtime_state
from app.contact.config import ContactSettings
from app.contact.models import Base, PORTFOLIO_SCHEMA
from app.runtime_env import RuntimeConfigError
import app.auth.models  # noqa: F401,E402
import app.admin.models  # noqa: F401,E402
import app.blog.models  # noqa: F401,E402


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # Offline mode only renders SQL; it never bootstraps or connects.
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=PORTFOLIO_SCHEMA,
    )
    context.execute(f"CREATE SCHEMA IF NOT EXISTS {PORTFOLIO_SCHEMA}")
    with context.begin_transaction():
        context.run_migrations()


def _refuse_target_overrides() -> None:
    # The target comes only from the runtime gate (design §4.4), never from -x or alembic.ini.
    if context.get_x_argument():
        raise RuntimeConfigError("alembic_override_refused", key="-x")
    if config.get_main_option("sqlalchemy.url"):
        raise RuntimeConfigError("alembic_override_refused", key="sqlalchemy.url")


def _connectable():
    state = runtime_state.bootstrap_runtime("alembic")
    if state.mode == "development":
        return runtime_db.create_development_engine(poolclass=pool.NullPool)
    # Attested production: today's connection parameters, unchanged.
    settings = ContactSettings.from_env()
    if settings.database_url:
        config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )


def run_migrations_online() -> None:
    _refuse_target_overrides()
    connectable = _connectable()
    with connectable.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {PORTFOLIO_SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=PORTFOLIO_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

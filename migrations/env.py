from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool, text

from app.contact.config import ContactSettings
from app.contact.models import Base, PORTFOLIO_SCHEMA
import app.auth.models  # noqa: F401,E402
import app.admin.models  # noqa: F401,E402
import app.blog.models  # noqa: F401,E402


load_dotenv()

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

settings = ContactSettings.from_env()
if settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=PORTFOLIO_SCHEMA,
    )
    context.execute(f"CREATE SCHEMA IF NOT EXISTS {PORTFOLIO_SCHEMA}")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
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

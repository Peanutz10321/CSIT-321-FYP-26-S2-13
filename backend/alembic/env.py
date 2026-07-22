"""
Alembic environment.

The database URL is never stored in alembic.ini. It is read from the same
`app.config.settings` the application uses, so migrations always target the
database the backend is configured for (.env, or .env.test when APP_ENV=test).
An explicit `-x db_url=...` overrides it, which is how the PostgreSQL tests
point Alembic at a throwaway database.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database import Base

# Importing every model registers its table on Base.metadata, which is what
# autogenerate diffs against. Keep this list in sync with app/main.py.
import app.models.user  # noqa: F401
import app.models.election  # noqa: F401
import app.models.election_key  # noqa: F401
import app.models.candidate  # noqa: F401
import app.models.election_voter  # noqa: F401
import app.models.ballot  # noqa: F401
import app.models.candidate_result  # noqa: F401
import app.models.audit_log  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Resolve the target database URL.

    Precedence: `-x db_url=...` (command line), then a url set programmatically
    on the config object (how the tests target a throwaway database), then the
    application settings. alembic.ini itself never carries a URL.
    """
    from_cli = context.get_x_argument(as_dictionary=True).get("db_url")
    if from_cli:
        return from_cli

    from_config = config.get_main_option("sqlalchemy.url", None)
    if from_config:
        return from_config

    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (used to review a migration)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # SQLite cannot ALTER most things in place; batch mode rewrites the
            # table instead. Harmless on PostgreSQL, which ignores it.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig

from alembic import context

# 接入应用的 metadata / 当前 engine
from app.db import Base, get_engine, get_sqlalchemy_url, uses_postgresql
from app import models  # noqa: F401  # 触发模型注册

config = context.config
# 覆盖 alembic.ini 中的占位 URL
config.set_main_option("sqlalchemy.url", get_sqlalchemy_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# SQLite 需要 render_as_batch 以支持 ALTER；PostgreSQL 不需要
_use_batch = config.attributes.get("render_as_batch")
if _use_batch is None:
    _use_batch = not uses_postgresql()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_use_batch,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        context.configure(
            connection=provided_connection,
            target_metadata=target_metadata,
            render_as_batch=_use_batch,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_use_batch,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# 接入应用的 engine / metadata
from app.config import config as app_config
from app.db import Base, engine
from app import models  # noqa: F401  # 触发模型注册

config = context.config
# 覆盖 alembic.ini 中的占位 URL
config.set_main_option("sqlalchemy.url", f"sqlite:///{app_config.db_path}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER 友好
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from alembic import context
from app import models  # noqa: F401
from app.core.database import Base, engine

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    context.configure(connection=config.attributes["connection"], target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

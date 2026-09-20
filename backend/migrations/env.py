from alembic import context
from tram.infrastructure.database import Base, make_engine
from tram.infrastructure.settings import Settings

config = context.config
target_metadata = Base.metadata


def run_migrations():
    url = Settings().database_url.get_secret_value()
    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run_migrations()

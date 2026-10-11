from alembic import context
from feya.config import settings
from feya.db import make_engine, metadata

with make_engine(settings.database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()

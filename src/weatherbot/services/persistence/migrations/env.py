# src/weatherbot/services/persistence/migrations/env.py
"""Alembic's environment, configured in code: the runtime needs no ``alembic.ini``.

``weatherbot.services.persistence.database`` hands over an open connection in
``config.attributes["connection"]``; the migrations run inside its transaction, in batch
mode, because SQLite alters a table by copying it. The database's engine opens every
transaction itself (pysqlite's own handling is off), so DDL is transactional: a failed
upgrade leaves nothing behind.
"""

from alembic import context
from sqlalchemy import Connection

from weatherbot.services.persistence.tables import Base


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
        transactional_ddl=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if not isinstance(connection, Connection):
    message = "open the database with weatherbot.services.persistence.database"
    raise TypeError(message)
_run(connection)

# src/weatherbot/services/persistence/__init__.py
"""The local SQLite database: its tables, migrations, opener, cache, and repositories.

Only ``weatherbot.services`` touches the database; an import-linter contract keeps
SQLAlchemy and Alembic out of every other layer.
"""

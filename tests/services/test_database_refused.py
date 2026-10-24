# tests/services/test_database_refused.py
"""When ``open_database`` refuses an unknown revision, ``serve`` sends one toast and exits 1."""

from cli_support import FakeToast, run, runtime
from sqlalchemy import text

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database


def test_unknown_database_revision_sends_one_database_free_toast_and_exits_1() -> None:
    paths = AppPaths.resolve()
    with open_database(paths) as database, database.engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999_future'"))

    toast = FakeToast(result="delivered")
    result = run(["serve"], runtime(toast=toast))

    assert result.exit_code == 1
    assert len(toast.handed) == 1
    sent = toast.handed[0]
    assert sent.id == 0
    assert sent.title == (
        "Weatherbot cannot open its database: unknown_revision; reinstall or restore it."
    )
    assert "unknown" in result.stderr.lower() or "revision" in result.stderr.lower()

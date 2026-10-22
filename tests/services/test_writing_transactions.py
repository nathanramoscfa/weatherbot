# tests/services/test_writing_transactions.py
"""Writing transactions begin IMMEDIATE, so two processes that write at once both succeed.

Two processes (``sys.executable`` with a short script, on the same temporary database)
each open a writing transaction, read, wait, and write, at the same moment. A deferred
``BEGIN`` would let both read first, and the second writer would then fail at once with
``database is locked``; ``BEGIN IMMEDIATE`` makes the second wait for the first to commit.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Final, cast

from fixture_support import REPOSITORY_ROOT
from sqlalchemy import event, select

from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import BUSY_TIMEOUT_MS, open_database
from weatherbot.services.persistence.repositories import SettingsRepository
from weatherbot.services.persistence.tables import SettingRow

WRITE: Final = """
import sys, time
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import func, select
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database, writing_session
from weatherbot.services.persistence.tables import SettingRow

data, go, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
with open_database(AppPaths(config_dir=data, data_dir=data)) as database:
    deadline = time.monotonic() + 60
    while not go.exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    with writing_session(database.engine) as session:
        seen = session.scalar(select(func.count()).select_from(SettingRow))
        time.sleep(0.5)
        session.add(SettingRow(key=name, value=seen, updated_at=datetime.now(UTC)))
"""
SERVICES: Final = REPOSITORY_ROOT / "src" / "weatherbot" / "services"
PLAIN_WRITE: Final = re.compile(r"Session\((?:self\._)?engine\)[^\n]*\.begin\(\)|engine\.begin\(\)")


def test_two_processes_writing_overlapping_transactions_both_succeed(tmp_path: Path) -> None:
    paths = AppPaths.resolve()
    with open_database(paths):  # created at the head first, so neither process migrates
        pass
    go = tmp_path / "go"
    processes = [
        subprocess.Popen(  # noqa: S603 - this interpreter, a constant script, test paths
            [sys.executable, "-c", WRITE, str(paths.data_dir), str(go), name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for name in ("first", "second")
    ]
    go.write_text("go", encoding="utf-8")
    errors = [process.communicate(timeout=120)[1] for process in processes]

    assert [process.returncode for process in processes] == [0, 0], [e[-300:] for e in errors]
    with open_database(paths) as database:
        repository = SettingsRepository(database.engine)
        seen = sorted(cast("int", repository.get(name)) for name in ("first", "second"))
    # The second transaction began after the first committed, so it saw the first's row.
    assert seen == [0, 1]


def test_writes_begin_immediate_and_reads_stay_deferred() -> None:
    begun: list[str] = []

    def capture(_connection: object, _cursor: object, statement: str, *_: object) -> None:
        if statement.startswith("BEGIN"):
            begun.append(statement)

    with open_database(AppPaths.resolve()) as database:
        event.listen(database.engine, "before_cursor_execute", capture)
        repository = SettingsRepository(database.engine)
        repository.set("probe", 1)
        assert repository.get("probe") == 1

    assert begun == ["BEGIN IMMEDIATE", "BEGIN"]


def test_the_busy_timeout_is_thirty_seconds() -> None:
    assert BUSY_TIMEOUT_MS == 30_000  # noqa: PLR2004 - the value under test
    with open_database(AppPaths.resolve()) as database, database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == BUSY_TIMEOUT_MS
        assert connection.execute(select(SettingRow.key)).all() == []


def test_no_service_opens_a_writing_transaction_without_immediate() -> None:
    plain = [
        f"{path.relative_to(SERVICES).as_posix()}: {match.group(0)}"
        for path in SERVICES.rglob("*.py")
        if "migrations" not in path.parts
        for match in PLAIN_WRITE.finditer(path.read_text(encoding="utf-8"))
    ]

    assert plain == []

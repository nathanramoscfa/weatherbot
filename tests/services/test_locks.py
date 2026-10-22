# tests/services/test_locks.py
"""The lock processes share: another process waits, a probe disturbs nothing, death frees it.

Every holder here is a real second process (``sys.executable`` running a short script),
because the operating system's lock is what is under test. Each script waits for a file
the test creates, so no test depends on how long a process takes to start.
"""

import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext

from weatherbot.services.config import AppPaths
from weatherbot.services.locks import LockBusyError, ProcessLock, held
from weatherbot.services.persistence.database import (
    alembic_config,
    create_database_engine,
    head_revision,
)

START_WAIT_S: Final = 60
HOLD: Final = """
import sys, time
from pathlib import Path
from weatherbot.services.locks import ProcessLock

lock_path, ready, stop = (Path(arg) for arg in sys.argv[1:4])
lock = ProcessLock(lock_path)
assert lock.try_acquire(), "the holder could not take the lock"
ready.write_text("held", encoding="utf-8")
deadline = time.monotonic() + 120
while not stop.exists() and time.monotonic() < deadline:
    time.sleep(0.05)
lock.release()
"""
OPEN: Final = """
import sys, time
from pathlib import Path
from weatherbot.services.config import AppPaths
from weatherbot.services.persistence.database import open_database

data, go = Path(sys.argv[1]), Path(sys.argv[2])
deadline = time.monotonic() + 60
while not go.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
with open_database(AppPaths(config_dir=data, data_dir=data)) as database:
    print(database.revision, database.backup_path is not None)
"""


def _python(script: str, *args: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603 - this interpreter, a constant script, test paths
        [sys.executable, "-c", script, *map(str, args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + START_WAIT_S
    while not path.exists():
        if process.poll() is not None:
            _, stderr = process.communicate()
            pytest.fail(f"the helper process exited early: {stderr[-400:]}")
        if time.monotonic() > deadline:
            pytest.fail("the helper process never got ready")
        time.sleep(0.02)


@contextmanager
def holder(lock_path: Path) -> Generator[subprocess.Popen[str]]:
    """Another process that holds the lock until the block ends."""
    ready, stop = lock_path.with_name("ready"), lock_path.with_name("stop")
    process = _python(HOLD, lock_path, ready, stop)
    try:
        _wait_for(ready, process)
        yield process
    finally:
        stop.write_text("stop", encoding="utf-8")
        process.communicate(timeout=START_WAIT_S)


def test_a_second_holder_waits_and_then_raises(tmp_path: Path) -> None:
    lock_path = tmp_path / "cycle.lock"
    with holder(lock_path):
        lock = ProcessLock(lock_path, poll_s=0.05)
        started = time.monotonic()
        with pytest.raises(LockBusyError, match=r"cycle\.lock"):
            lock.acquire(wait_s=0.4)
        waited = time.monotonic() - started

    assert waited >= 0.4  # noqa: PLR2004 - the wait asked for
    assert not lock.locked


def test_a_probe_neither_truncates_the_lock_file_nor_reads_the_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "cycle.lock"
    lock_path.write_bytes(b"written before the holder")
    opened: list[str] = []
    real_open = os.open

    def recording_open(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        opened.append(Path(path).name)
        return real_open(path, flags, mode)

    with holder(lock_path):
        sidecar = ProcessLock(lock_path).info_path
        assert sidecar.read_text(encoding="utf-8").startswith("pid ")
        monkeypatch.setattr(os, "open", recording_open)
        assert held(lock_path)
        monkeypatch.undo()

    assert opened == ["cycle.lock"]
    assert lock_path.read_bytes() == b"written before the holder"


def test_held_is_false_for_a_free_or_missing_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "cycle.lock"

    assert not held(lock_path)
    assert not lock_path.exists()
    lock_path.touch()
    assert not held(lock_path)


@pytest.mark.anyio
async def test_acquire_async_lets_other_tasks_run_while_it_waits(tmp_path: Path) -> None:
    lock_path = tmp_path / "cycle.lock"
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.02)

    with holder(lock_path):
        ticker = asyncio.create_task(tick())
        with pytest.raises(LockBusyError):
            await ProcessLock(lock_path, poll_s=0.05).acquire_async(wait_s=0.5)
        ticker.cancel()

    assert ticks >= 10  # noqa: PLR2004 - about 25 in half a second, unless the wait blocked


def test_the_lock_is_released_when_the_holding_process_dies(tmp_path: Path) -> None:
    lock_path = tmp_path / "cycle.lock"
    with holder(lock_path) as process:
        assert held(lock_path)
        process.kill()
        process.wait(timeout=START_WAIT_S)
        lock = ProcessLock(lock_path, poll_s=0.05)
        lock.acquire(wait_s=10)

    assert lock.locked
    lock.release()
    assert not held(lock_path)


def test_two_processes_opening_a_database_behind_the_head_migrate_it_once(
    tmp_path: Path,
) -> None:
    paths = AppPaths.resolve()
    paths.data_dir.mkdir(parents=True)
    engine = create_database_engine(paths.database_path)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0004")
    engine.dispose()
    go = tmp_path / "go"
    processes = [_python(OPEN, paths.data_dir, go) for _ in range(2)]
    go.write_text("go", encoding="utf-8")
    finished = [process.communicate(timeout=120) for process in processes]

    assert [process.returncode for process in processes] == [0, 0], [e for _, e in finished]
    revisions = sorted(out.split() for out, _ in finished)
    assert revisions == [[head_revision(), "False"], [head_revision(), "True"]]
    assert len(list(paths.backup_dir.iterdir())) == 1
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == head_revision()
    engine.dispose()

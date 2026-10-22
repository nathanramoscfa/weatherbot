# src/weatherbot/services/locks.py
"""A lock that processes share: the operating system's lock on a file's first byte.

``ProcessLock(path)`` takes an exclusive lock on the first byte of a file that is used for
nothing else: ``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere, standard library
only. The file is opened without truncating it, because a Windows lock is mandatory and a
second opener must not disturb the holder. The operating system releases the lock when the
holding process ends, however it ends, so a lock is never left behind by a crash.

The holder writes its process id and the instant it took the lock to a sidecar
``<path>.info``, after taking it, for a person reading the data directory; nothing reads
the sidecar to decide anything, and a probe never opens it. ``acquire`` waits by sleeping
and ``acquire_async`` by ``asyncio.sleep``, so an event loop keeps running while it waits;
past the wait, both raise ``LockBusyError``. ``held(path)`` says whether another process
holds a lock, trying once without waiting.

The monitor cycle holds ``cycle.lock`` and a migration ``migrate.lock``, both in the data
directory (``AppPaths``).
"""

import asyncio
import contextlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from weatherbot.services.config import ensure_directory

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

INFO_SUFFIX: Final = ".info"
DEFAULT_POLL_S: Final = 0.5


class LockBusyError(Exception):
    """Another process held the lock for the whole wait."""


def _lock_byte(descriptor: int) -> bool:
    """Try once to lock a file's first byte; whether the lock was taken."""
    if sys.platform == "win32":
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_byte(descriptor: int) -> None:
    if sys.platform == "win32":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _take(path: Path) -> int | None:
    """Open the lock file without truncating it and lock it; the descriptor, or ``None``."""
    ensure_directory(path.parent)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT)
    if _lock_byte(descriptor):
        return descriptor
    os.close(descriptor)
    return None


def _give_back(descriptor: int) -> None:
    try:
        _unlock_byte(descriptor)
    finally:
        os.close(descriptor)


def held(path: Path) -> bool:
    """Whether another process holds the lock on ``path``, trying once without waiting.

    The probe takes the lock and gives it back at once when it is free; it never
    truncates the file and never reads the holder's sidecar.

    Args:
        path: The lock file.

    Returns:
        Whether the lock is held elsewhere; ``False`` when the file does not exist.
    """
    if not path.exists():
        return False
    descriptor = _take(path)
    if descriptor is None:
        return True
    _give_back(descriptor)
    return False


class ProcessLock:
    """An exclusive lock on a file, shared by every process on the machine."""

    def __init__(self, path: Path, *, poll_s: float = DEFAULT_POLL_S) -> None:
        """Create the lock; nothing is opened until it is acquired.

        Args:
            path: The lock file, used for nothing else.
            poll_s: How long to sleep between tries while waiting.
        """
        self._path = path
        self._poll_s = poll_s
        self._descriptor: int | None = None

    @property
    def path(self) -> Path:
        """The lock file."""
        return self._path

    @property
    def info_path(self) -> Path:
        """The sidecar that names the holder, for diagnostics only."""
        return self._path.with_name(f"{self._path.name}{INFO_SUFFIX}")

    @property
    def locked(self) -> bool:
        """Whether this object holds the lock."""
        return self._descriptor is not None

    def try_acquire(self) -> bool:
        """Try once to take the lock, without waiting.

        Returns:
            Whether this object now holds it.
        """
        if self._descriptor is not None:
            return True
        self._descriptor = _take(self._path)
        if self._descriptor is None:
            return False
        started = datetime.now(UTC).isoformat()
        self.info_path.write_text(f"pid {os.getpid()}\nsince {started}\n", encoding="utf-8")
        return True

    def acquire(self, wait_s: float) -> None:
        """Take the lock, retrying until ``wait_s`` has passed.

        Args:
            wait_s: How long to wait for another holder, in seconds.

        Raises:
            LockBusyError: Another process held it for the whole wait.
        """
        deadline = time.monotonic() + wait_s
        while not self.try_acquire():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockBusyError(self._busy())
            time.sleep(min(self._poll_s, remaining))

    async def acquire_async(self, wait_s: float) -> None:
        """Take the lock, retrying until ``wait_s`` has passed, never blocking the loop.

        Args:
            wait_s: How long to wait for another holder, in seconds.

        Raises:
            LockBusyError: Another process held it for the whole wait.
        """
        deadline = time.monotonic() + wait_s
        while not self.try_acquire():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockBusyError(self._busy())
            await asyncio.sleep(min(self._poll_s, remaining))

    def release(self) -> None:
        """Give the lock back; releasing a lock not held does nothing."""
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        # Another process may have the sidecar open; it is diagnostics only.
        with contextlib.suppress(OSError):
            self.info_path.unlink(missing_ok=True)
        _give_back(descriptor)

    def _busy(self) -> str:
        return f"another process holds {self._path.name}"

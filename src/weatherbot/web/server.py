# src/weatherbot/web/server.py
"""Embedded uvicorn server running on the caller's asyncio loop without signal capture."""

import asyncio
import logging
import socket
import sys
from collections.abc import Awaitable, Callable, Generator, Sequence
from contextlib import contextmanager, suppress
from typing import Final, cast, override

import uvicorn
from fastapi import FastAPI

LOGGER: Final = logging.getLogger("weatherbot.web.server")
DEFAULT_BIND_RETRIES: Final = 5
DEFAULT_RETRY_DELAY_S: Final = 2.0
CONCURRENCY_LIMIT: Final = 64
GRACEFUL_SHUTDOWN_TIMEOUT_S: Final = 2


class EmbeddedUvicornServer(uvicorn.Server):
    """``uvicorn.Server`` subclass that leaves signal handling to ``weatherbot serve``."""

    def __init__(self, config: uvicorn.Config, started_event: asyncio.Event) -> None:
        """Store ``config`` and the ``started_event`` to set once listening."""
        super().__init__(config)
        self._started_event = started_event

    @override
    @contextmanager
    def capture_signals(self) -> Generator[None]:
        """Leave ``SIGINT`` and ``SIGTERM`` to the outer CLI runner."""
        yield

    @override
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Start listening on ``sockets`` and signal ``started_event``."""
        await super().startup(sockets=sockets)
        if self.started:
            self._started_event.set()


def _bind_address(host: str) -> tuple[socket.AddressFamily, str]:
    if host == "::1":
        return socket.AF_INET6, "::1"
    if host == "localhost":
        return socket.AF_INET, "127.0.0.1"
    return socket.AF_INET, host


def _create_bound_socket(host: str, port: int) -> socket.socket:
    family, bind_host = _bind_address(host)
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
        sock.set_inheritable(False)
    except BaseException:
        sock.close()
        raise
    return sock


class WebServer:
    """Embedded loopback HTTP server for ``weatherbot serve``."""

    def __init__(  # noqa: PLR0913 - configurable retry and shutdown hooks
        self,
        app: FastAPI,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        before_stop: Sequence[Callable[[], object]] = (),
        retries: int | None = None,
        retry_delay_s: float | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        socket_factory: Callable[[str, int], socket.socket] | None = None,
    ) -> None:
        """Create the embedded server for ``app`` on ``host`` and ``port``."""
        self.app = app
        self.host = host
        self.port = port
        self.before_stop: tuple[Callable[[], object], ...] = tuple(before_stop)
        self.retries = retries
        self.retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._socket_factory = socket_factory
        self.bound_port: int | None = None
        self.started = asyncio.Event()
        self._uvicorn_server: EmbeddedUvicornServer | None = None

    @property
    def address(self) -> str:
        """Return the ``http://<host>:<port>`` dashboard URL."""
        effective_port = self.bound_port if self.bound_port is not None else self.port
        host_text = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host_text}:{effective_port}"

    async def _bind_with_retry(self) -> socket.socket | None:
        max_retries = DEFAULT_BIND_RETRIES if self.retries is None else self.retries
        delay_s = DEFAULT_RETRY_DELAY_S if self.retry_delay_s is None else self.retry_delay_s
        factory = _create_bound_socket if self._socket_factory is None else self._socket_factory
        last_error: OSError | None = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                await self._sleep(delay_s)
            try:
                return factory(self.host, self.port)
            except OSError as error:
                last_error = error
        error_name = type(last_error).__name__ if last_error is not None else "OSError"
        LOGGER.warning("the web server could not start: %s", error_name)
        return None

    async def serve(self, stop: asyncio.Event) -> None:
        """Bind the loopback socket and serve ``app`` until ``stop`` is set or cancelled."""
        sock = await self._bind_with_retry()
        if sock is None:
            return

        try:
            sockname: object = sock.getsockname()
            if isinstance(sockname, tuple):
                addr_parts = cast("tuple[object, ...]", sockname)
                if len(addr_parts) >= 2 and isinstance(addr_parts[1], int):  # noqa: PLR2004
                    self.bound_port = addr_parts[1]
            _, bind_host = _bind_address(self.host)
            config = uvicorn.Config(
                self.app,
                host=bind_host,
                port=self.bound_port or self.port,
                log_config=None,
                access_log=False,
                server_header=False,
                proxy_headers=False,
                lifespan="off",
                limit_concurrency=CONCURRENCY_LIMIT,
                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_S,
            )
            server = EmbeddedUvicornServer(config, self.started)
            self._uvicorn_server = server

            async def _run_uvicorn() -> None:
                try:
                    await server.serve(sockets=[sock])
                except (OSError, SystemExit) as error:
                    LOGGER.warning("the web server could not start: %s", type(error).__name__)

            server_task = asyncio.create_task(_run_uvicorn())
            stop_task = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait(
                    {server_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not stop_task.done():
                    stop_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await stop_task
                for hook in self.before_stop:
                    hook()
                server.should_exit = True
                with suppress(asyncio.CancelledError):
                    await server_task
        finally:
            sock.close()

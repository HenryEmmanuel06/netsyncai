"""Single-instance guard + local IPC.

The first agent process listens on a loopback port. Later launches (e.g.
Windows opening a netsync://pair?code=… link) connect, hand over their
message, and exit — so only one agent ever runs per user.

Messages are single text lines: "show", "quit", or a netsync:// URL.
Anything a local process can send here only opens a confirmation window
or quits the agent; no command can pair or share without the user.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

log = logging.getLogger("netsync.instance")

HOST = "127.0.0.1"
PORT = 47631
MAX_MSG = 2048


def send_to_running(message: str, timeout: float = 1.5) -> bool:
    """Deliver `message` to an already-running agent. False if none."""
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as s:
            s.sendall(message.encode("utf-8")[:MAX_MSG] + b"\n")
            return s.recv(16).startswith(b"ok")
    except OSError:
        return False


class InstanceServer:
    def __init__(self, on_message: Callable[[str], None]):
        self._on_message = on_message
        self._sock: socket.socket | None = None

    def try_acquire(self) -> bool:
        """Bind the port. False means another agent already owns it."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((HOST, PORT))
        except OSError:
            s.close()
            return False
        s.listen(4)
        self._sock = s
        threading.Thread(target=self._serve, name="ipc", daemon=True).start()
        return True

    def _serve(self) -> None:
        assert self._sock is not None
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    data = conn.recv(MAX_MSG).decode("utf-8", "replace").strip()
                    conn.sendall(b"ok\n")
                except OSError:
                    continue
            if data:
                try:
                    self._on_message(data)
                except Exception:
                    log.exception("ipc handler failed")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()

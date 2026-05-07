"""Unix domain socket IPC for communication between pytest and the Ren'Py engine."""
from __future__ import annotations

import os
import socket
from typing import Any

from pytest_renpy.engine.protocol import deserialize, serialize


class IPCClient:
    """Pytest-side IPC client. Connects to the engine's socket."""

    def __init__(self, socket_path: str, timeout: float = 30.0):
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect(self.socket_path)

    def send_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        self._send(cmd)
        return self._recv()

    def send(self, data: dict[str, Any]) -> None:
        self._send(data)

    def recv(self) -> dict[str, Any]:
        return self._recv()

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send(self, data: dict[str, Any]) -> None:
        if not self._sock:
            raise ConnectionError("Not connected")
        self._sock.sendall(serialize(data).encode("utf-8"))

    def _recv(self) -> dict[str, Any]:
        if not self._sock:
            raise ConnectionError("Not connected")
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(8192)
            except socket.timeout:
                raise TimeoutError("IPC read timed out")
            if not chunk:
                raise ConnectionError("IPC connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return deserialize(line.decode("utf-8"))


class IPCServer:
    """Engine-side IPC server. Listens for a single client connection.

    Compatible with Python 3.9 (Ren'Py's bundled Python).
    """

    def __init__(self, socket_path: str, timeout: float = 30.0):
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._buf = b""

    def bind_and_listen(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.bind(self.socket_path)
        self._sock.listen(1)

    def accept(self) -> None:
        if not self._sock:
            raise ConnectionError("Server not bound")
        self._conn, _ = self._sock.accept()
        self._conn.settimeout(self.timeout)

    def receive_command(self) -> dict[str, Any]:
        return self._recv()

    def send_response(self, data: dict[str, Any]) -> None:
        self._send(data)

    def close(self) -> None:
        for s in (self._conn, self._sock):
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        self._conn = None
        self._sock = None
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

    def _send(self, data: dict[str, Any]) -> None:
        if not self._conn:
            raise ConnectionError("No client connected")
        self._conn.sendall(serialize(data).encode("utf-8"))

    def _recv(self) -> dict[str, Any]:
        if not self._conn:
            raise ConnectionError("No client connected")
        while b"\n" not in self._buf:
            try:
                chunk = self._conn.recv(8192)
            except socket.timeout:
                raise TimeoutError("IPC read timed out")
            if not chunk:
                raise ConnectionError("IPC connection closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return deserialize(line.decode("utf-8"))

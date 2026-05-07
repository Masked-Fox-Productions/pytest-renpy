"""Ren'Py engine subprocess management.

Launches a headless Ren'Py process with the test harness injected,
establishes IPC connection, and manages the subprocess lifecycle.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pytest_renpy.engine.ipc import IPCServer


class EngineError(Exception):
    """Raised when the Ren'Py engine fails to start, crashes, or returns an error."""


class RenpyEngine:
    """Manages a headless Ren'Py subprocess for integration testing."""

    def __init__(
        self,
        sdk_path: str | Path,
        project_path: str | Path,
        timeout: float = 30.0,
    ):
        self.sdk_path = Path(sdk_path).resolve()
        self.project_path = Path(project_path).resolve()
        self.timeout = timeout

        self._process: subprocess.Popen | None = None
        self._ipc: IPCServer | None = None
        self._tmp_dir: str | None = None
        self._tmp_project: Path | None = None
        self._save_dir: str | None = None
        self._socket_path: str | None = None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        sdk_python = self._find_sdk_python()
        renpy_main = self.sdk_path / "renpy.py"
        if not renpy_main.exists():
            raise EngineError(f"renpy.py not found in SDK at {self.sdk_path}")

        if not self.project_path.is_dir():
            raise EngineError(f"Project directory not found: {self.project_path}")

        game_dir = self.project_path / "game"
        if not game_dir.is_dir():
            raise EngineError(
                f"No 'game' subdirectory in project: {self.project_path}"
            )

        self._tmp_dir = tempfile.mkdtemp(prefix="renpy_test_")
        self._tmp_project = Path(self._tmp_dir) / "project"
        self._save_dir = os.path.join(self._tmp_dir, "saves")
        self._socket_path = os.path.join(self._tmp_dir, "test.sock")
        os.makedirs(self._save_dir)

        tmp_game = self._tmp_project / "game"
        shutil.copytree(game_dir, tmp_game, symlinks=True)

        harness_src = Path(__file__).parent / "_test_harness.rpy"
        shutil.copy2(harness_src, tmp_game / "_test_harness.rpy")

        for rpyc in tmp_game.rglob("*.rpyc"):
            rpyc.unlink()

        self._ipc = IPCServer(self._socket_path, timeout=self.timeout)
        self._ipc.bind_and_listen()

        env = os.environ.copy()
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
        env["RENPY_TEST_SOCKET"] = self._socket_path
        env["RENPY_TEST_SAVEDIR"] = self._save_dir
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)

        self._process = subprocess.Popen(
            [str(sdk_python), str(renpy_main), str(self._tmp_project)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            self._ipc.accept()
            msg = self._ipc.receive_command()
            if msg.get("status") != "ready":
                raise EngineError(f"Engine sent unexpected status: {msg}")
        except TimeoutError:
            stderr = self._capture_stderr()
            self.stop()
            raise EngineError(
                f"Engine failed to connect within {self.timeout}s.\n{stderr}"
            )
        except Exception:
            self.stop()
            raise

    def send_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        self._check_alive()
        self._ipc.send_response(cmd)
        try:
            return self._ipc.receive_command()
        except ConnectionError:
            stderr = self._capture_stderr()
            raise EngineError(f"Engine died during command.\n{stderr}")

    def send(self, data: dict[str, Any]) -> None:
        self._check_alive()
        self._ipc.send_response(data)

    def recv(self) -> dict[str, Any]:
        self._check_alive()
        try:
            return self._ipc.receive_command()
        except ConnectionError:
            stderr = self._capture_stderr()
            raise EngineError(f"Engine died.\n{stderr}")

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            try:
                if self._ipc and self._ipc._conn:
                    self._ipc.send_response({"cmd": "stop"})
                    self._process.wait(timeout=5)
            except Exception:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()

        if self._ipc:
            self._ipc.close()
            self._ipc = None

        if self._tmp_dir and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

        self._process = None
        self._tmp_project = None

    def _check_alive(self) -> None:
        if not self.is_alive:
            stderr = self._capture_stderr()
            raise EngineError(f"Engine process is not running.\n{stderr}")

    def _capture_stderr(self) -> str:
        if self._process and self._process.stderr:
            try:
                return self._process.stderr.read().decode("utf-8", errors="replace")[
                    :3000
                ]
            except Exception:
                pass
        return ""

    def _find_sdk_python(self) -> Path:
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "linux":
            if machine in ("x86_64", "amd64"):
                subdir = "py3-linux-x86_64"
            elif machine == "aarch64":
                subdir = "py3-linux-aarch64"
            else:
                subdir = f"py3-linux-{machine}"
        elif system == "darwin":
            subdir = "py3-mac-universal"
        elif system == "windows":
            subdir = "py3-windows-x86_64"
        else:
            subdir = f"py3-{system}-{machine}"

        python_name = "python.exe" if system == "windows" else "python"
        python_path = self.sdk_path / "lib" / subdir / python_name

        if not python_path.exists():
            candidates = list((self.sdk_path / "lib").glob("py3-*/python*"))
            if candidates:
                python_path = candidates[0]
            else:
                raise EngineError(
                    f"SDK Python not found at {python_path}. "
                    f"Searched {self.sdk_path / 'lib'}"
                )

        return python_path

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

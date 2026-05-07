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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pytest_renpy.engine.ipc import IPCServer


class EngineError(Exception):
    """Raised when the Ren'Py engine fails to start, crashes, or returns an error."""


@dataclass
class NavigationResult:
    at_label: str | None
    yield_type: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdvanceResult:
    status: str
    ticks_elapsed: int
    at_label: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MenuResult:
    choice: str
    index: int
    raw: dict[str, Any] = field(default_factory=dict)


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
        self._pending_menu: dict[str, Any] | None = None
        self._last_menu_options: list[dict[str, str]] = []

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
        env["RENPY_LESS_UPDATES"] = "1"
        env["RENPY_SIMPLE_EXCEPTIONS"] = "1"
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
            resp = self._ipc.receive_command()
        except ConnectionError:
            stderr = self._capture_stderr()
            raise EngineError(f"Engine died.\n{stderr}")
        if resp.get("status") == "menu_waiting":
            self._pending_menu = resp
            self._last_menu_options = resp.get("options", [])
        else:
            self._pending_menu = None
        return resp

    # --- Navigation Commands (Unit 4) ---

    def jump(self, label: str) -> NavigationResult:
        self.send({"cmd": "jump", "label": label})
        resp = self._recv_navigation()
        return NavigationResult(
            at_label=resp.get("at_label"),
            yield_type=resp.get("yield_type", ""),
            raw=resp,
        )

    def call(self, label: str) -> NavigationResult:
        self.send({"cmd": "call", "label": label})
        resp = self._recv_navigation()
        return NavigationResult(
            at_label=resp.get("at_label"),
            yield_type=resp.get("yield_type", ""),
            raw=resp,
        )

    def advance(self, ticks: int = 1) -> AdvanceResult:
        total = 0
        last_resp = None
        for _ in range(ticks):
            self.send({"cmd": "continue"})
            resp = self.recv()
            last_resp = resp
            total += 1
            if resp.get("status") == "menu_waiting":
                break
        return AdvanceResult(
            status=last_resp.get("status", ""),
            ticks_elapsed=total,
            at_label=last_resp.get("at_label") if last_resp else None,
            raw=last_resp or {},
        )

    def advance_until(
        self,
        label: str | None = None,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        max_ticks: int = 1000,
    ) -> AdvanceResult:
        for tick in range(1, max_ticks + 1):
            self.send({"cmd": "continue"})
            resp = self.recv()

            if resp.get("status") == "menu_waiting":
                if label is None and condition is None:
                    return AdvanceResult(
                        status="menu_waiting",
                        ticks_elapsed=tick,
                        at_label=resp.get("at_label"),
                        raw=resp,
                    )

            at = resp.get("at_label")
            if label is not None and at == label:
                return AdvanceResult(
                    status="reached",
                    ticks_elapsed=tick,
                    at_label=at,
                    raw=resp,
                )

            if condition is not None:
                store = self.get_store()
                if condition(store):
                    return AdvanceResult(
                        status="reached",
                        ticks_elapsed=tick,
                        at_label=at,
                        raw=resp,
                    )

        return AdvanceResult(
            status="timeout",
            ticks_elapsed=max_ticks,
            at_label=resp.get("at_label") if resp else None,
            raw=resp or {},
        )

    def _recv_navigation(self) -> dict[str, Any]:
        resp = self.recv()
        if resp.get("status") == "error":
            raise EngineError(resp.get("message", "Engine error"))
        return resp

    # --- State Inspection Commands (Unit 5) ---

    def get_store(self, *var_names: str) -> dict[str, Any]:
        if not var_names:
            resp = self.send_command({"cmd": "get_store", "vars": []})
        else:
            resp = self.send_command({"cmd": "get_store", "vars": list(var_names)})
        status = resp.get("status")
        if status == "error":
            raise EngineError(resp.get("message", "get_store error"))
        if status != "ok":
            raise EngineError(f"Protocol desync: get_store got status '{status}'")
        return resp.get("values", {})

    def get_terminal_log(self) -> list[str] | None:
        store = self.get_store("terminal_log")
        return store.get("terminal_log")

    def get_available_commands(self) -> dict[str, Any] | None:
        store = self.get_store("cmd_dict")
        return store.get("cmd_dict")

    # --- Menu Interaction and Store Mutation (Unit 6) ---

    def get_menu_options(self) -> list[dict[str, str]]:
        return self._pending_menu.get("options", []) if self._pending_menu else []

    def select_menu(self, choice: int | str = 0) -> MenuResult:
        if isinstance(choice, str):
            options = self.get_menu_options()
            for i, opt in enumerate(options):
                if opt.get("text") == choice:
                    choice = i
                    break
            else:
                raise EngineError(f"Menu option not found: {choice!r}")

        self.send({"cmd": "menu_select", "index": choice})
        resp = self.recv()
        self._pending_menu = None
        text = ""
        if self._last_menu_options and 0 <= choice < len(self._last_menu_options):
            text = self._last_menu_options[choice].get("text", "")

        if resp.get("status") == "menu_waiting":
            self._pending_menu = resp
            self._last_menu_options = resp.get("options", [])

        return MenuResult(choice=text, index=choice, raw=resp)

    def set_store(self, **kwargs: Any) -> None:
        resp = self.send_command({"cmd": "set_store", "vars": kwargs})
        status = resp.get("status")
        if status == "error":
            raise EngineError(resp.get("message", "set_store error"))
        if status != "ok":
            raise EngineError(f"Protocol desync: set_store got status '{status}'")

    def exec_code(self, code: str) -> dict[str, Any] | None:
        self._check_alive()
        self._ipc.send_response({"cmd": "exec", "code": code})
        try:
            resp = self._ipc.receive_command()
        except ConnectionError:
            stderr = self._capture_stderr()
            raise EngineError(f"Engine died during exec.\n{stderr}")
        if resp.get("status") == "error":
            raise EngineError(resp.get("message", "exec error"))
        if resp.get("status") == "menu_waiting":
            self._pending_menu = resp
            self._last_menu_options = resp.get("options", [])
            return resp
        if resp.get("status") in ("yielded", "completed"):
            self._pending_menu = None
            return resp
        return None

    def eval_expr(self, expr: str) -> Any:
        resp = self.send_command({"cmd": "eval", "expr": expr})
        status = resp.get("status")
        if status == "error":
            raise EngineError(resp.get("message", "eval error"))
        if status != "ok":
            raise EngineError(f"Protocol desync: eval got status '{status}'")
        return resp.get("result")

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

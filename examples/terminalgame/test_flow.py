"""Layer 2 integration tests for terminalgame.

Demonstrates: label flow, store mutation, game-specific input adapters.

NOTE: terminalgame has parse errors (global declaration after assignment
in display.rpy) that cause the Ren'Py parser to exit before the harness
can boot. These tests are marked xfail until the game's parse errors
are resolved. Layer 2 correctly runs inside Ren'Py's bundled Python 3.9,
which accepts the syntax — but the parser still flags it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import EngineError, RenpyEngine

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
PROJECT_PATH = Path("/projects/xander/terminalgame")

requires_sdk = pytest.mark.skipif(not SDK_PATH.exists(), reason="SDK not found")
requires_project = pytest.mark.skipif(
    not PROJECT_PATH.exists(), reason="terminalgame not found"
)


@requires_sdk
@requires_project
class TestTerminalgameFlow:
    @pytest.mark.xfail(
        reason="terminalgame has parse errors that prevent headless boot",
        raises=(EngineError, ConnectionError),
    )
    def test_fenton_initialize_sets_terminal_log(self):
        """Jump to fenton_initialize, verify game_print output appears in terminal_log."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            engine.jump("fenton_initialize")
            store = engine.get_store("terminal_log")
            log = store.get("terminal_log")
            assert log is not None
            assert any(
                "management framework" in str(entry).lower()
                for entry in log
            )

    @pytest.mark.xfail(
        reason="terminalgame has parse errors that prevent headless boot",
        raises=(EngineError, ConnectionError),
    )
    def test_store_mutation_via_set_store(self):
        """Use set_store to inject a value, verify the engine sees it."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            engine.set_store(x_test_value=42)
            store = engine.get_store("x_test_value")
            assert store["x_test_value"] == 42

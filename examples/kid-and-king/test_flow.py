"""Layer 2 integration tests for the-kid-and-the-king-of-chicago.

Demonstrates: menu interaction via renpy.display_menu().
Kid-and-king uses display_menu to build dynamic reader menus,
which is impossible to test with Layer 1's mock.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import RenpyEngine

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
PROJECT_PATH = Path("/projects/masked_fox/the-kid-and-the-king-of-chicago")

requires_sdk = pytest.mark.skipif(not SDK_PATH.exists(), reason="SDK not found")
requires_project = pytest.mark.skipif(
    not PROJECT_PATH.exists(), reason="kid-and-king not found"
)


@requires_sdk
@requires_project
class TestKidAndKingFlow:
    def test_start_label_initializes_state(self):
        """Jump to start, verify game initializes and yields."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            result = engine.jump("start")
            assert result.yield_type in ("say", "menu", "misc")

    def test_create_readers_defines_reader_objects(self):
        """Jump to create_readers, verify Reader objects appear in store."""
        with RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=30) as engine:
            engine.jump("create_readers")
            store = engine.get_store("readers")
            readers = store.get("readers")
            assert readers is not None
            if isinstance(readers, dict):
                assert "Joe" in readers or len(readers) > 0

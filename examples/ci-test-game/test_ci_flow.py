"""CI Layer 2 integration tests using the bundled ci-test-game.

Exercises: label navigation, variable access, menu interaction.
These tests run in CI with an autodiscovered SDK from ~/.renpy-sdk/.
"""
from __future__ import annotations

import pytest


class TestCiGameFlow:
    def test_jump_and_get_store(self, renpy_engine):
        result = renpy_engine.jump("set_vars")
        store = renpy_engine.get_store("x", "y")
        assert store["x"] == 42
        assert store["y"] == 99

    def test_start_label(self, renpy_engine):
        result = renpy_engine.call("start")
        store = renpy_engine.get_store("visited_start")
        assert store["visited_start"] is True

    def test_menu_interaction(self, renpy_engine):
        result = renpy_engine.jump("menu_test")
        assert result.raw.get("status") == "menu_waiting"
        options = renpy_engine.get_menu_options()
        assert len(options) == 2
        renpy_engine.select_menu("Apple")
        store = renpy_engine.get_store("choice_made")
        assert store["choice_made"] == "apple"

    def test_multi_step_advance(self, renpy_engine):
        renpy_engine.call("multi_step")
        store = renpy_engine.get_store("x")
        assert store["x"] == 3

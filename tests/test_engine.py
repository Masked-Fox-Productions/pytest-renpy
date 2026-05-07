"""Tests for the Ren'Py engine runner and harness."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import (
    AdvanceResult,
    EngineError,
    MenuResult,
    NavigationResult,
    RenpyEngine,
)

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
FIXTURE_GAME = Path(__file__).parent.parent / "spike" / "fixture_game"

requires_sdk = pytest.mark.skipif(
    not SDK_PATH.exists(), reason="Ren'Py SDK not found"
)
requires_fixture = pytest.mark.skipif(
    not FIXTURE_GAME.exists(), reason="Fixture game not found"
)


class TestEngineRunner:
    @requires_sdk
    @requires_fixture
    def test_boot_ping_stop(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            resp = engine.send_command({"cmd": "ping"})
            assert resp["status"] == "pong"

    @requires_sdk
    @requires_fixture
    def test_engine_is_alive(self):
        engine = RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15)
        assert not engine.is_alive
        engine.start()
        assert engine.is_alive
        engine.stop()
        assert not engine.is_alive

    @requires_sdk
    @requires_fixture
    def test_temp_project_not_original(self):
        engine = RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15)
        engine.start()
        try:
            assert engine._tmp_project is not None
            assert engine._tmp_project != engine.project_path
            harness_in_tmp = engine._tmp_project / "game" / "_test_harness.rpy"
            assert harness_in_tmp.exists()
        finally:
            engine.stop()

    @requires_sdk
    @requires_fixture
    def test_original_project_unmodified(self):
        orig_files = set(
            f.name for f in (FIXTURE_GAME / "game").iterdir()
        )
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send_command({"cmd": "ping"})
        after_files = set(
            f.name for f in (FIXTURE_GAME / "game").iterdir()
        )
        assert orig_files == after_files

    @requires_sdk
    @requires_fixture
    def test_temp_cleanup_on_stop(self):
        engine = RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15)
        engine.start()
        tmp_dir = engine._tmp_dir
        assert os.path.exists(tmp_dir)
        engine.stop()
        assert not os.path.exists(tmp_dir)

    @requires_sdk
    @requires_fixture
    def test_stop_already_dead(self):
        engine = RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15)
        engine.start()
        engine._process.kill()
        engine._process.wait()
        engine.stop()

    @requires_sdk
    @requires_fixture
    def test_context_manager(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            resp = engine.send_command({"cmd": "ping"})
            assert resp["status"] == "pong"

    def test_invalid_sdk_path(self, tmp_path):
        with pytest.raises(EngineError, match="SDK Python not found"):
            engine = RenpyEngine(tmp_path / "fake_sdk", tmp_path)
            engine.start()

    def test_invalid_project_path(self, tmp_path):
        with pytest.raises(EngineError, match="Project directory not found"):
            engine = RenpyEngine(SDK_PATH, tmp_path / "nonexistent")
            engine.start()

    @requires_sdk
    def test_project_without_game_dir(self, tmp_path):
        with pytest.raises(EngineError, match="No 'game' subdirectory"):
            engine = RenpyEngine(SDK_PATH, tmp_path)
            engine.start()


class TestHarnessIntegration:
    @requires_sdk
    @requires_fixture
    def test_jump_and_store_mutation(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send({"cmd": "jump", "label": "set_x"})
            resp = engine.recv()
            assert resp["status"] == "yielded"

            resp = engine.send_command({"cmd": "get_store", "vars": ["x"]})
            assert resp["values"]["x"] == 42

    @requires_sdk
    @requires_fixture
    def test_pause_yield(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send({"cmd": "jump", "label": "set_y"})
            resp = engine.recv()
            assert resp["status"] == "yielded"
            assert resp["yield_type"] == "pause"

            resp = engine.send_command({"cmd": "get_store", "vars": ["y"]})
            assert resp["values"]["y"] == 99

    @requires_sdk
    @requires_fixture
    def test_menu_interaction(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send({"cmd": "jump", "label": "menu_test"})
            resp = engine.recv()
            assert resp["status"] == "menu_waiting"
            assert len(resp["options"]) == 2
            assert resp["options"][0]["text"] == "Apple"
            assert resp["options"][1]["text"] == "Banana"

            engine.send({"cmd": "menu_select", "index": 1})
            resp = engine.recv()
            assert resp["status"] == "yielded"

            resp = engine.send_command(
                {"cmd": "get_store", "vars": ["choice_made"]}
            )
            assert resp["values"]["choice_made"] == "banana"

    @requires_sdk
    @requires_fixture
    def test_set_store(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            resp = engine.send_command(
                {"cmd": "set_store", "vars": {"x": 999}}
            )
            assert resp["status"] == "ok"

            resp = engine.send_command(
                {"cmd": "get_store", "vars": ["x"]}
            )
            assert resp["values"]["x"] == 999

    @requires_sdk
    @requires_fixture
    def test_fresh_process_isolation(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send({"cmd": "jump", "label": "set_x"})
            engine.recv()
            resp = engine.send_command({"cmd": "get_store", "vars": ["x"]})
            assert resp["values"]["x"] == 42

        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            resp = engine.send_command({"cmd": "get_store", "vars": ["x"]})
            assert resp["values"]["x"] == 0

    @requires_sdk
    @requires_fixture
    def test_jump_nonexistent_label(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.send({"cmd": "jump", "label": "does_not_exist"})
            # Engine should crash or return error
            with pytest.raises(EngineError):
                engine.recv()


class TestNavigationAPI:
    @requires_sdk
    @requires_fixture
    def test_jump_returns_navigation_result(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.jump("set_x")
            assert isinstance(result, NavigationResult)
            assert result.yield_type == "say"

    @requires_sdk
    @requires_fixture
    def test_jump_store_mutation(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("set_x")
            store = engine.get_store("x")
            assert store["x"] == 42

    @requires_sdk
    @requires_fixture
    def test_advance(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("set_x")
            result = engine.advance(1)
            assert isinstance(result, AdvanceResult)
            assert result.ticks_elapsed == 1

    @requires_sdk
    @requires_fixture
    def test_advance_until_timeout(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("set_x")
            result = engine.advance_until(
                label="nonexistent_label", max_ticks=3
            )
            assert result.status == "timeout"
            assert result.ticks_elapsed == 3


class TestStateInspection:
    @requires_sdk
    @requires_fixture
    def test_get_store_multiple_vars(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("set_x")
            store = engine.get_store("x", "y")
            assert store["x"] == 42
            assert store["y"] == 0

    @requires_sdk
    @requires_fixture
    def test_get_store_nonexistent_var(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            store = engine.get_store("no_such_variable")
            assert store["no_such_variable"] is None

    @requires_sdk
    @requires_fixture
    def test_set_store(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.set_store(x=123, y=456)
            store = engine.get_store("x", "y")
            assert store["x"] == 123
            assert store["y"] == 456


class TestMenuAPI:
    @requires_sdk
    @requires_fixture
    def test_jump_to_menu_and_select_by_index(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.jump("menu_test")
            assert result.raw.get("status") == "menu_waiting"

            options = engine.get_menu_options()
            assert len(options) == 2
            assert options[0]["text"] == "Apple"

            menu_result = engine.select_menu(1)
            assert isinstance(menu_result, MenuResult)
            assert menu_result.choice == "Banana"
            assert menu_result.index == 1

            store = engine.get_store("choice_made")
            assert store["choice_made"] == "banana"

    @requires_sdk
    @requires_fixture
    def test_select_menu_by_text(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("menu_test")
            menu_result = engine.select_menu("Apple")
            assert menu_result.choice == "Apple"
            assert menu_result.index == 0

            store = engine.get_store("choice_made")
            assert store["choice_made"] == "apple"

    @requires_sdk
    @requires_fixture
    def test_select_menu_invalid_text(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            engine.jump("menu_test")
            with pytest.raises(EngineError, match="Menu option not found"):
                engine.select_menu("Cherry")


class TestAutoAdvance:
    @requires_sdk
    @requires_fixture
    def test_call_auto_advances_says(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_with_says")
            assert result.yield_type == "completed"
            store = engine.get_store("call_result")
            assert store["call_result"] == "after"

    @requires_sdk
    @requires_fixture
    def test_call_nested_auto_advances(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_nested")
            assert result.yield_type == "completed"
            store = engine.get_store("call_result", "inner_result")
            assert store["call_result"] == "outer_done"
            assert store["inner_result"] == "inner_done"

    @requires_sdk
    @requires_fixture
    def test_call_with_jump_auto_advances_through(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_with_jump")
            # Jump doesn't pop the call frame, so auto-advance continues
            # through jump_target (say auto-advanced) and into call_with_menu
            # where the menu yields to IPC
            assert result.raw.get("status") == "menu_waiting"
            store = engine.get_store("call_result")
            assert store["call_result"] == "jumped"

    @requires_sdk
    @requires_fixture
    def test_call_with_menu_pauses(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_with_menu")
            assert result.raw.get("status") == "menu_waiting"
            menu_result = engine.select_menu(0)
            assert menu_result.raw.get("status") == "completed"
            store = engine.get_store("call_result", "choice_made")
            assert store["call_result"] == "menu_done"
            assert store["choice_made"] == "option_a"

    @requires_sdk
    @requires_fixture
    def test_call_no_yields_completes(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_no_yields")
            assert result.yield_type == "completed"
            store = engine.get_store("call_result")
            assert store["call_result"] == "no_yield_done"

    @requires_sdk
    @requires_fixture
    def test_jump_still_yields_at_every_point(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.jump("set_x")
            assert result.yield_type == "say"
            assert result.raw.get("status") == "yielded"

    @requires_sdk
    @requires_fixture
    def test_exec_code_with_call_completes(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            resp = engine.exec_code("trigger_call()")
            assert resp is not None
            assert resp.get("status") == "completed"
            store = engine.get_store("exec_result")
            assert store["exec_result"] == "exec_call_done"

    @requires_sdk
    @requires_fixture
    def test_call_then_jump_no_stale_state(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_no_yields")
            assert result.yield_type == "completed"
            result = engine.jump("set_x")
            assert result.raw.get("status") == "yielded"
            assert result.yield_type == "say"

    @requires_sdk
    @requires_fixture
    def test_sequential_calls_both_complete(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result1 = engine.call("call_with_says")
            assert result1.yield_type == "completed"
            store1 = engine.get_store("call_result")
            assert store1["call_result"] == "after"

            engine.set_store(call_result="", inner_result="")
            result2 = engine.call("call_nested")
            assert result2.yield_type == "completed"
            store2 = engine.get_store("call_result", "inner_result")
            assert store2["call_result"] == "outer_done"
            assert store2["inner_result"] == "inner_done"

    @requires_sdk
    @requires_fixture
    def test_call_paused_then_jump_cancels(self):
        with RenpyEngine(SDK_PATH, FIXTURE_GAME, timeout=15) as engine:
            result = engine.call("call_with_menu")
            assert result.raw.get("status") == "menu_waiting"
            # Instead of selecting menu, jump somewhere else
            result = engine.jump("set_x")
            assert result.raw.get("status") == "yielded"
            assert result.yield_type == "say"
            store = engine.get_store("x")
            assert store["x"] == 42

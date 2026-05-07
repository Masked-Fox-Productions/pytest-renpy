"""Comprehensive tests for the mock Ren'Py namespace (Unit 3)."""

import pytest

from pytest_renpy import JumpException, CallException, ReturnException, QuitException
from pytest_renpy.mock_renpy import create_mock, MockRenpy
from pytest_renpy.mock_renpy.store import StoreNamespace
from pytest_renpy.mock_renpy.config import MockConfig
from pytest_renpy.mock_renpy.persistent import MockPersistent
from pytest_renpy.mock_renpy.display import (
    Transform,
    TintMatrix,
    Character,
    Dissolve,
    dissolve,
    fade,
    right,
    left,
)
from pytest_renpy.mock_renpy.random import MockRandom


# ---------------------------------------------------------------------------
# MockRenpy: control flow exports
# ---------------------------------------------------------------------------


class TestJump:
    def test_jump_raises_jump_exception(self):
        mock = create_mock()
        with pytest.raises(JumpException) as exc_info:
            mock.jump("target")
        assert exc_info.value.target == "target"

    def test_jump_records_target(self):
        mock = create_mock()
        with pytest.raises(JumpException):
            mock.jump("some_label")
        assert mock.jumps == ["some_label"]

    def test_multiple_jumps_recorded(self):
        mock = create_mock()
        for label in ["a", "b", "c"]:
            with pytest.raises(JumpException):
                mock.jump(label)
        assert mock.jumps == ["a", "b", "c"]


class TestCall:
    def test_call_raises_call_exception(self):
        mock = create_mock()
        with pytest.raises(CallException) as exc_info:
            mock.call("target")
        assert exc_info.value.target == "target"

    def test_call_records_target(self):
        mock = create_mock()
        with pytest.raises(CallException):
            mock.call("subroutine")
        assert mock.calls == ["subroutine"]


class TestReturnStatement:
    def test_return_raises_return_exception(self):
        mock = create_mock()
        with pytest.raises(ReturnException):
            mock.return_statement()


class TestQuit:
    def test_quit_raises_quit_exception(self):
        mock = create_mock()
        with pytest.raises(QuitException):
            mock.quit()

    def test_quit_sets_quit_called(self):
        mock = create_mock()
        with pytest.raises(QuitException):
            mock.quit()
        assert mock.quit_called is True

    def test_quit_called_starts_false(self):
        mock = create_mock()
        assert mock.quit_called is False


class TestPause:
    def test_pause_does_not_raise(self):
        mock = create_mock()
        mock.pause(0.2)  # Should not raise

    def test_pause_records_duration(self):
        mock = create_mock()
        mock.pause(0.2)
        mock.pause(1.5)
        assert mock.pauses == [0.2, 1.5]


class TestNotify:
    def test_notify_records_message(self):
        mock = create_mock()
        mock.notify("Game saved!")
        assert mock.notifications == ["Game saved!"]


class TestDisplayMenu:
    def test_display_menu_returns_first_option_value(self):
        mock = create_mock()
        result = mock.display_menu([("Option A", "a"), ("Option B", "b")])
        assert result == "a"

    def test_display_menu_records_options(self):
        mock = create_mock()
        options = [("Option A", "a"), ("Option B", "b")]
        mock.display_menu(options)
        assert mock.menus == [options]

    def test_display_menu_skips_none_values(self):
        mock = create_mock()
        result = mock.display_menu([("Caption", None), ("Real Option", "x")])
        assert result == "x"


class TestSceneShowHide:
    def test_scene_records_call(self):
        mock = create_mock()
        mock.scene()
        assert len(mock.scenes) == 1

    def test_show_records_name_and_at_list(self):
        mock = create_mock()
        mock.show("character", at_list=[right])
        assert len(mock.shown) == 1
        assert mock.shown[0]["name"] == "character"
        assert mock.shown[0]["at_list"] == [right]

    def test_show_records_name_without_at_list(self):
        mock = create_mock()
        mock.show("bg_forest")
        assert mock.shown[0]["name"] == "bg_forest"
        assert mock.shown[0]["at_list"] == []

    def test_hide_records_name(self):
        mock = create_mock()
        mock.hide("character")
        assert mock.hidden == [{"name": "character"}]


class TestWithStatement:
    def test_with_statement_records_transition(self):
        mock = create_mock()
        mock.with_statement(dissolve)
        assert mock.transitions == [dissolve]


class TestVersion:
    def test_version_returns_string(self):
        mock = create_mock()
        result = mock.version()
        assert isinstance(result, str)
        assert len(result) > 0


class TestPermissiveFallback:
    def test_unimplemented_attr_returns_callable(self):
        mock = create_mock()
        stub = mock.some_unimplemented_api
        assert callable(stub)

    def test_unimplemented_attr_callable_returns_none(self):
        mock = create_mock()
        result = mock.some_unimplemented_api("arg1", key="val")
        assert result is None

    def test_unimplemented_attr_does_not_raise(self):
        mock = create_mock()
        # Should not raise AttributeError
        mock.music.play("track.ogg")


# ---------------------------------------------------------------------------
# MockRandom
# ---------------------------------------------------------------------------


class TestMockRandom:
    def test_randint_deterministic_with_default_seed(self):
        mock = create_mock()
        value = mock.random.randint(0, 9)
        assert isinstance(value, int)
        assert 0 <= value <= 9

    def test_randint_reproducible_after_reseed(self):
        mock = create_mock()
        mock.random.seed(42)
        seq1 = [mock.random.randint(0, 100) for _ in range(5)]
        mock.random.seed(42)
        seq2 = [mock.random.randint(0, 100) for _ in range(5)]
        assert seq1 == seq2

    def test_default_seed_produces_same_sequence(self):
        r1 = MockRandom(seed=0)
        r2 = MockRandom(seed=0)
        seq1 = [r1.randint(0, 100) for _ in range(10)]
        seq2 = [r2.randint(0, 100) for _ in range(10)]
        assert seq1 == seq2


# ---------------------------------------------------------------------------
# StoreNamespace
# ---------------------------------------------------------------------------


class TestStoreNamespace:
    def test_attribute_and_dict_access(self):
        store = StoreNamespace()
        store.x = 42
        assert store["x"] == 42
        assert store.x == 42

    def test_dict_and_attribute_access(self):
        store = StoreNamespace()
        store["y"] = "hello"
        assert store.y == "hello"

    def test_attribute_error_for_missing(self):
        store = StoreNamespace()
        with pytest.raises(AttributeError):
            _ = store.nonexistent

    def test_key_error_for_missing(self):
        store = StoreNamespace()
        with pytest.raises(KeyError):
            _ = store["nonexistent"]

    def test_del_attr(self):
        store = StoreNamespace()
        store.x = 1
        del store.x
        with pytest.raises(AttributeError):
            _ = store.x

    def test_dict_methods_preserved(self):
        """Built-in dict methods should work, not be shadowed by key lookups."""
        store = StoreNamespace()
        store["a"] = 1
        store["b"] = 2
        # dict.keys() should work
        assert set(store.keys()) == {"a", "b"}
        # dict.values() should work
        assert set(store.values()) == {1, 2}
        # dict.items() should work
        assert set(store.items()) == {("a", 1), ("b", 2)}

    def test_dict_method_not_shadowed_by_key(self):
        """If a key named 'items' is set, dict.items() still works."""
        store = StoreNamespace()
        store["items"] = "my_value"
        # dict.items() method should still be accessible
        result = dict.items(store)
        assert ("items", "my_value") in result
        # Attribute access should return the stored value since
        # __getattr__ is only called after dict method lookup fails
        # But 'items' IS a dict method, so store.items returns the method
        assert callable(store.items)

    def test_is_valid_dict_for_exec(self):
        """StoreNamespace works as globals dict in exec()."""
        store = StoreNamespace()
        exec("x = 42", store)
        assert store["x"] == 42
        assert store.x == 42

    def test_globals_returns_store_in_exec(self):
        """globals() inside exec'd code returns the StoreNamespace."""
        store = StoreNamespace()
        exec("g = globals()", store)
        assert store["g"] is store

    def test_exec_function_def_and_call(self):
        """Functions defined in exec'd code are accessible via the store."""
        store = StoreNamespace()
        code = """
def greet(name):
    return f"Hello, {name}!"
"""
        exec(code, store)
        assert store.greet("World") == "Hello, World!"


# ---------------------------------------------------------------------------
# MockPersistent
# ---------------------------------------------------------------------------


class TestMockPersistent:
    def test_attribute_assignment(self):
        p = MockPersistent()
        p.save_data = {"key": "value"}
        assert p.save_data == {"key": "value"}

    def test_unset_attribute_returns_none(self):
        p = MockPersistent()
        assert p.anything is None

    def test_delete_attribute(self):
        p = MockPersistent()
        p.x = 1
        del p.x
        assert p.x is None  # Returns None after deletion


# ---------------------------------------------------------------------------
# Display stubs
# ---------------------------------------------------------------------------


class TestTransform:
    def test_transform_records_kwargs(self):
        t = Transform(matrixcolor=TintMatrix("#ff0000"), zoom=1.7)
        assert t.zoom == 1.7
        assert isinstance(t.matrixcolor, TintMatrix)
        assert t.kwargs["zoom"] == 1.7

    def test_transform_repr(self):
        t = Transform(xalign=0.5)
        assert "Transform" in repr(t)


class TestTintMatrix:
    def test_tint_matrix_records_color(self):
        tm = TintMatrix("#ff0000")
        assert tm.color == "#ff0000"

    def test_tint_matrix_repr(self):
        tm = TintMatrix("#00ff00")
        assert "#00ff00" in repr(tm)


class TestCharacter:
    def test_character_returns_callable(self):
        c = Character("Vince", color="#8B2A3A")
        assert callable(c)

    def test_character_stores_name_and_kwargs(self):
        c = Character("Vince", color="#8B2A3A")
        assert c.name == "Vince"
        assert c.color == "#8B2A3A"

    def test_character_callable_returns_none(self):
        c = Character("Vince")
        result = c("Hello there!")
        assert result is None


class TestDissolve:
    def test_dissolve_records_duration(self):
        d = Dissolve(0.5)
        assert d.duration == 0.5


class TestTransitionConstants:
    def test_dissolve_constant_exists(self):
        assert dissolve is not None
        assert repr(dissolve) == "dissolve"

    def test_fade_constant_exists(self):
        assert fade is not None
        assert repr(fade) == "fade"


class TestPositionConstants:
    def test_right_constant(self):
        assert right is not None
        assert repr(right) == "right"

    def test_left_constant(self):
        assert left is not None
        assert repr(left) == "left"


# ---------------------------------------------------------------------------
# MockConfig
# ---------------------------------------------------------------------------


class TestMockConfig:
    def test_gamedir_returns_default(self):
        c = MockConfig()
        assert isinstance(c.gamedir, str)

    def test_savedir_returns_default(self):
        c = MockConfig()
        assert isinstance(c.savedir, str)

    def test_unknown_attr_returns_none(self):
        c = MockConfig()
        result = c.anything_at_all
        assert result is None  # Does not raise AttributeError

    def test_rollback_enabled_default(self):
        c = MockConfig()
        assert c.rollback_enabled is True


# ---------------------------------------------------------------------------
# Integration tests: exec with mock renpy
# ---------------------------------------------------------------------------


class TestExecIntegration:
    def test_exec_jump_propagates(self):
        """exec'd code calling renpy.jump raises JumpException."""
        mock = create_mock()
        store = StoreNamespace()
        store["renpy"] = mock

        code = 'renpy.jump("x")'
        with pytest.raises(JumpException) as exc_info:
            exec(code, store)
        assert exc_info.value.target == "x"
        assert mock.jumps == ["x"]

    def test_exec_globals_dynamic_dispatch(self):
        """globals()[name](args) dispatch works in exec'd code."""
        store = StoreNamespace()
        code_define = """
def greet(name):
    return f"Hello, {name}!"
"""
        exec(code_define, store)

        code_dispatch = """
result = globals()["greet"]("World")
"""
        exec(code_dispatch, store)
        assert store["result"] == "Hello, World!"

    def test_exec_function_uses_globals(self):
        """Functions defined in exec'd code share the store as globals."""
        mock = create_mock()
        store = StoreNamespace()
        store["renpy"] = mock

        code = """
counter = 0

def increment():
    global counter
    counter += 1
    return counter
"""
        exec(code, store)
        assert store.increment() == 1
        assert store.increment() == 2
        assert store["counter"] == 2

    def test_exec_with_character_and_transform(self):
        """Character and Transform are usable in exec'd code."""
        store = StoreNamespace()
        store["Character"] = Character
        store["Transform"] = Transform

        code = """
v = Character("Vince", color="#8B2A3A")
center_left = Transform(xalign=0.35, yalign=1.0, zoom=0.9)
"""
        exec(code, store)
        assert callable(store["v"])
        assert store["center_left"].xalign == 0.35

    def test_exec_with_mock_renpy_full(self):
        """Full integration: exec code using multiple renpy features."""
        mock = create_mock()
        store = StoreNamespace()
        store["renpy"] = mock
        store["Character"] = Character

        code = """
narrator = Character(None)
version_str = renpy.version()
renpy.pause(0.1)
"""
        exec(code, store)
        assert callable(store["narrator"])
        assert isinstance(store["version_str"], str)
        assert mock.pauses == [0.1]


class TestCreateMockFreshness:
    def test_each_mock_is_independent(self):
        """create_mock() returns fresh instances with no shared state."""
        m1 = create_mock()
        m2 = create_mock()

        with pytest.raises(JumpException):
            m1.jump("a")

        assert m1.jumps == ["a"]
        assert m2.jumps == []

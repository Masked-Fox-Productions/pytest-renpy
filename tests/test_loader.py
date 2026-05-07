"""Tests for project loader."""

import sys
from pathlib import Path

import pytest

from pytest_renpy import JumpException, QuitException
from pytest_renpy.loader import ProjectData, load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace


@pytest.fixture
def game_dir(tmp_path):
    """Create a temporary game directory with .rpy files."""
    return tmp_path


def write_rpy(directory, filename, content):
    """Helper to write a .rpy file."""
    p = directory / filename
    p.write_text(content, encoding="utf-8")
    return p


class TestLoadProject:
    def test_single_file_one_init_block(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    x = 42\n",
        )
        project = load_project(game_dir)
        assert len(project.init_blocks) == 1
        assert project.init_blocks[0].code == "x = 42"

    def test_multiple_files_collected(self, game_dir):
        write_rpy(game_dir, "a.rpy", "init python:\n    a = 1\n")
        write_rpy(game_dir, "b.rpy", "init python:\n    b = 2\n")
        project = load_project(game_dir)
        assert len(project.init_blocks) == 2

    def test_priority_sorting(self, game_dir):
        write_rpy(
            game_dir,
            "late.rpy",
            "init 100 python:\n    late = True\n",
        )
        write_rpy(
            game_dir,
            "early.rpy",
            "init python:\n    early = True\n",
        )
        project = load_project(game_dir)
        assert project.init_blocks[0].priority == 0
        assert project.init_blocks[1].priority == 100

    def test_same_priority_sorted_by_filename(self, game_dir):
        write_rpy(game_dir, "z_file.rpy", "init python:\n    z = 1\n")
        write_rpy(game_dir, "a_file.rpy", "init python:\n    a = 1\n")
        project = load_project(game_dir)
        assert "a_file" in project.init_blocks[0].source_file
        assert "z_file" in project.init_blocks[1].source_file

    def test_defines_collected(self, game_dir):
        write_rpy(game_dir, "script.rpy", 'define v = Character("Vince")\n')
        project = load_project(game_dir)
        assert len(project.defines) == 1
        assert project.defines[0].name == "v"

    def test_defaults_collected(self, game_dir):
        write_rpy(game_dir, "script.rpy", "default score = 0\n")
        project = load_project(game_dir)
        assert len(project.defaults) == 1
        assert project.defaults[0].name == "score"

    def test_labels_collected(self, game_dir):
        write_rpy(game_dir, "script.rpy", "label start:\n    pass\n")
        project = load_project(game_dir)
        assert len(project.labels) == 1
        assert project.labels[0].name == "start"

    def test_empty_directory(self, game_dir):
        project = load_project(game_dir)
        assert project.init_blocks == []
        assert project.defines == []
        assert project.defaults == []
        assert project.labels == []

    def test_file_with_no_init_blocks(self, game_dir):
        write_rpy(game_dir, "dialogue.rpy", 'label start:\n    "Hello world"\n')
        project = load_project(game_dir)
        assert project.init_blocks == []
        assert len(project.labels) == 1

    def test_recursive_glob(self, game_dir):
        subdir = game_dir / "subdir"
        subdir.mkdir()
        write_rpy(subdir, "nested.rpy", "init python:\n    nested = True\n")
        project = load_project(game_dir)
        assert len(project.init_blocks) == 1

    def test_game_dir_stored(self, game_dir):
        project = load_project(game_dir)
        assert project.game_dir == game_dir


class TestExecuteInto:
    def test_basic_execution(self, game_dir):
        write_rpy(game_dir, "script.rpy", "init python:\n    x = 42\n")
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["x"] == 42

    def test_mock_renpy_injected(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    version = renpy.version()\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert isinstance(ns["version"], str)

    def test_custom_mock_injected(self, game_dir):
        write_rpy(game_dir, "script.rpy", "init python:\n    pass\n")
        project = load_project(game_dir)
        ns = StoreNamespace()
        mock = create_mock()
        project.execute_into(ns, mock_renpy=mock)
        assert ns["renpy"] is mock

    def test_character_available(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            'define v = Character("Vince", color="#8B2A3A")\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["v"].name == "Vince"

    def test_transform_available(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "define pos = Transform(xalign=0.5)\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["pos"].xalign == 0.5

    def test_defines_applied_after_init_blocks(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            'init python:\n    base_color = "#fff"\n\ndefine my_char = Character("Test", color=base_color)\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["my_char"].name == "Test"
        assert ns["my_char"].color == "#fff"

    def test_defaults_applied(self, game_dir):
        write_rpy(game_dir, "script.rpy", "default score = 0\n")
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["score"] == 0

    def test_defaults_do_not_overwrite_existing(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    score = 100\n\ndefault score = 0\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["score"] == 100

    def test_cross_file_function_calls(self, game_dir):
        write_rpy(
            game_dir,
            "a_utils.rpy",
            "init python:\n    def double(n):\n        return n * 2\n",
        )
        write_rpy(
            game_dir,
            "b_main.rpy",
            "init python:\n    result = double(21)\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["result"] == 42

    def test_globals_dispatch(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n"
            "    def greet(name):\n"
            "        return f'hello {name}'\n"
            "    result = globals()['greet']('world')\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["result"] == "hello world"

    def test_jump_raises_exception(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            'init python:\n    def go():\n        renpy.jump("target")\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        with pytest.raises(JumpException) as exc_info:
            ns["go"]()
        assert exc_info.value.target == "target"

    def test_exec_error_includes_source_context(self, game_dir):
        write_rpy(
            game_dir,
            "broken.rpy",
            "init python:\n    x = undefined_variable\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        with pytest.raises(RuntimeError, match="broken.rpy"):
            project.execute_into(ns)

    def test_persistent_available(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            'default persistent.save_data = None\n\ninit python:\n    persistent.flag = True\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["persistent"].flag is True

    def test_display_constants_available(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    pos = right\n    trans = dissolve\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert repr(ns["pos"]) == "right"
        assert repr(ns["trans"]) == "dissolve"


class TestSysPathScoping:
    def test_sys_path_added_during_exec(self, game_dir):
        (game_dir / "helper.py").write_text("HELPER_VALUE = 99\n", encoding="utf-8")
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    from helper import HELPER_VALUE\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        game_dir_str = str(game_dir)

        project.execute_into(ns)

        assert ns["HELPER_VALUE"] == 99
        assert game_dir_str not in sys.path

    def test_sys_path_cleaned_on_error(self, game_dir):
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    raise ValueError('boom')\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        game_dir_str = str(game_dir)

        with pytest.raises(RuntimeError):
            project.execute_into(ns)

        assert game_dir_str not in sys.path

    def test_sys_path_not_duplicated(self, game_dir):
        write_rpy(game_dir, "script.rpy", "init python:\n    x = 1\n")
        project = load_project(game_dir)

        game_dir_str = str(game_dir)
        sys.path.insert(0, game_dir_str)
        try:
            ns = StoreNamespace()
            project.execute_into(ns)
            assert sys.path.count(game_dir_str) == 1
        finally:
            sys.path.remove(game_dir_str)


class TestIntegrationWithTerminalgame:
    """Integration tests against the real terminalgame project, if available."""

    TERMINALGAME_DIR = Path("/projects/xander/terminalgame/game")

    @pytest.fixture
    def terminalgame(self):
        if not self.TERMINALGAME_DIR.exists():
            pytest.skip("terminalgame not available")
        return load_project(self.TERMINALGAME_DIR)

    def test_loads_all_files(self, terminalgame):
        assert len(terminalgame.init_blocks) > 0
        assert len(terminalgame.labels) > 0

    def test_execute_produces_callable_functions(self, terminalgame):
        ns = StoreNamespace()
        mock = create_mock()
        try:
            terminalgame.execute_into(ns, mock_renpy=mock)
        except SyntaxError:
            pytest.skip(
                "terminalgame has Python 3.12+ incompatible global declarations"
            )
        assert callable(ns.get("game_print"))
        assert callable(ns.get("check_for_commands"))
        assert callable(ns.get("create_cmd"))
        assert isinstance(ns.get("cmd_dict"), dict)

    def test_game_print_works(self, terminalgame):
        ns = StoreNamespace()
        mock = create_mock()
        try:
            terminalgame.execute_into(ns, mock_renpy=mock)
        except SyntaxError:
            pytest.skip(
                "terminalgame has Python 3.12+ incompatible global declarations"
            )
        ns["game_print"]("hello from test")
        assert "hello from test" in ns["terminal_log"]

    def test_globals_dispatch_works(self, terminalgame):
        ns = StoreNamespace()
        mock = create_mock()
        try:
            terminalgame.execute_into(ns, mock_renpy=mock)
        except SyntaxError:
            pytest.skip(
                "terminalgame has Python 3.12+ incompatible global declarations"
            )
        with pytest.raises(QuitException):
            ns["check_for_commands"]("quit")

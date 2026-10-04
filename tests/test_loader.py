"""Tests for project loader."""

import sys
import types
from pathlib import Path

import pytest

from pytest_renpy import JumpException, QuitException
from pytest_renpy.loader import ProjectData, load_project
from pytest_renpy.mock_renpy import MockPersistent, create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace
from pytest_renpy.rpy_parser import ParseError


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

    def test_defaults_overwrite_init_code(self, game_dir):
        """Like Ren'Py at game start, a default wins over init-time assignment."""
        write_rpy(
            game_dir,
            "script.rpy",
            "init python:\n    score = 100\n\ndefault score = 0\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        assert ns["score"] == 0

    def test_defaults_do_not_overwrite_caller_preseeded(self, game_dir):
        write_rpy(game_dir, "script.rpy", "default score = 0\n")
        project = load_project(game_dir)
        ns = StoreNamespace(score=100)
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


def load_ns(game_dir, on_error="raise", **kwargs):
    """Load the project in game_dir and execute it into a fresh namespace."""
    project = load_project(game_dir)
    ns = kwargs.pop("namespace", None) or StoreNamespace()
    errors = project.execute_into(ns, on_error=on_error, **kwargs)
    return ns, errors


class TestInitStreamOrdering:
    def test_init_block_reads_earlier_define_in_same_file(self, game_dir):
        write_rpy(
            game_dir, "a.rpy", "define X = 5\ninit python:\n    y = X * 2\n"
        )
        ns, _ = load_ns(game_dir)
        assert ns["y"] == 10

    def test_define_priority_honored(self, game_dir):
        write_rpy(
            game_dir, "a.rpy", "define 5 X = 1\ninit python:\n    y = X\n"
        )
        with pytest.raises(RuntimeError, match="name 'X' is not defined"):
            load_ns(game_dir)

    def test_init_offset_beats_filename_order(self, game_dir):
        write_rpy(game_dir, "aa_game.rpy", "init python:\n    y = G\n")
        write_rpy(game_dir, "zz_gui.rpy", "init offset = -2\ndefine G = 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["y"] == 1

    def test_persistent_default_applies_in_stream(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "default persistent.seen = {}\n"
            "init python:\n"
            "    persistent.seen['intro'] = True\n",
        )
        ns, _ = load_ns(game_dir)
        assert ns["persistent"].seen == {"intro": True}

    def test_label_nested_persistent_default_visible_to_later_file(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "label setup:\n    default persistent.flags = set()\n",
        )
        write_rpy(game_dir, "b.rpy", "init python:\n    persistent.flags.add(1)\n")
        ns, _ = load_ns(game_dir)
        assert ns["persistent"].flags == {1}

    def test_ordinary_defaults_ordered_by_priority(self, game_dir):
        write_rpy(game_dir, "zz.rpy", "default -1 base = 10\n")
        write_rpy(game_dir, "aa.rpy", "default derived = base * 2\n")
        ns, _ = load_ns(game_dir)
        assert ns["derived"] == 20

    def test_ordinary_defaults_ordered_by_file(self, game_dir):
        write_rpy(game_dir, "aa.rpy", "default first = 1\n")
        write_rpy(game_dir, "zz.rpy", "default second = first + 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["second"] == 2

    def test_init_offset_applies_to_defaults(self, game_dir):
        write_rpy(game_dir, "zz.rpy", "init offset = -5\ndefault early = 1\n")
        write_rpy(game_dir, "aa.rpy", "default late = early + 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["late"] == 2

    def test_ordinary_defaults_run_after_all_init(self, game_dir):
        write_rpy(game_dir, "a.rpy", "default d = LATE\n")
        write_rpy(game_dir, "b.rpy", "init 999 python:\n    LATE = 'late'\n")
        ns, _ = load_ns(game_dir)
        assert ns["d"] == "late"

    def test_file_order_uses_relative_path_without_suffix(self, game_dir):
        sub = game_dir / "sub"
        sub.mkdir()
        write_rpy(game_dir, "a-b.rpy", "init python:\n    order.append('a-b')\n")
        write_rpy(game_dir, "a.rpy", "init python:\n    order.append('a')\n")
        write_rpy(sub, "x.rpy", "init python:\n    order.append('sub/x')\n")
        write_rpy(game_dir, "0.rpy", "init -1 python:\n    order = []\n")
        ns, _ = load_ns(game_dir)
        assert ns["order"] == ["a", "a-b", "sub/x"]


class TestNamespaceTargets:
    def test_define_config_sets_attribute(self, game_dir):
        write_rpy(game_dir, "a.rpy", 'define config.name = "Game"\n')
        ns, _ = load_ns(game_dir)
        assert ns["config"].name == "Game"
        assert "config.name" not in ns
        assert ns["renpy"].config is ns["config"]

    def test_default_persistent_on_fresh(self, game_dir):
        write_rpy(game_dir, "a.rpy", "default persistent.seen = 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["persistent"].seen == 1

    def test_default_persistent_keeps_existing(self, game_dir):
        write_rpy(game_dir, "a.rpy", "default persistent.seen = 1\n")
        p = MockPersistent()
        p.seen = 5
        ns, _ = load_ns(game_dir, persistent=p)
        assert ns["persistent"] is p
        assert p.seen == 5

    def test_define_persistent_set_if_none(self, game_dir):
        write_rpy(game_dir, "a.rpy", "define persistent.flag = 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["persistent"].flag == 1
        p = MockPersistent()
        p.flag = 5
        load_ns(game_dir, persistent=p)
        assert p.flag == 5

    def test_named_store_default_creates_holder(self, game_dir):
        write_rpy(game_dir, "a.rpy", "default mystore.score = 0\n")
        ns, _ = load_ns(game_dir)
        assert ns["mystore"].score == 0

    def test_named_store_default_respects_caller_value(self, game_dir):
        write_rpy(game_dir, "a.rpy", "default mystore.score = 0\n")
        ns = StoreNamespace(mystore=types.SimpleNamespace(score=3))
        load_ns(game_dir, namespace=ns)
        assert ns["mystore"].score == 3

    def test_named_store_default_overwrites_init_value(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "init python:\n"
            "    import types\n"
            "    mystore = types.SimpleNamespace(score=3)\n"
            "default mystore.score = 0\n",
        )
        ns, _ = load_ns(game_dir)
        assert ns["mystore"].score == 0

    def test_multilevel_define(self, game_dir):
        write_rpy(game_dir, "a.rpy", "define a.b.c = 1\n")
        ns, _ = load_ns(game_dir)
        assert ns["a"].b.c == 1

    def test_define_into_plain_dict_is_error(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "init python:\n    gamedata = {}\n\ndefine gamedata.x = 1\n",
        )
        with pytest.raises(RuntimeError, match=r"a\.rpy:4"):
            load_ns(game_dir)

    def test_default_overwrites_injected_builtin(self, game_dir):
        write_rpy(
            game_dir, "a.rpy", "init python:\n    x = 1\ndefault x = 2\ndefault build = []\n"
        )
        ns, _ = load_ns(game_dir)
        assert ns["x"] == 2
        assert ns["build"] == []

    @pytest.mark.parametrize(
        "line",
        [
            "define preferences.text_cps = 1",
            "define renpy.foo = 1",
            "default renpy.foo = 1",
            "default config.x = 1",
        ],
    )
    def test_forbidden_namespace_targets(self, game_dir, line):
        write_rpy(game_dir, "a.rpy", "\n" + line + "\n")
        with pytest.raises(RuntimeError, match=r"a\.rpy:2"):
            load_ns(game_dir)
        ns, errors = load_ns(game_dir, on_error="skip")
        assert len(errors) == 1
        assert errors[0][0].source_line == 2

    def test_define_operators(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "define items = [1]\ndefine items += [2]\ndefine flags = {1}\ndefine flags |= {2}\n",
        )
        ns, _ = load_ns(game_dir)
        assert ns["items"] == [1, 2]
        assert ns["flags"] == {1, 2}

    def test_transform_name_defined(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "transform slide_down:\n"
            "    yoffset -50\n"
            "define slide_in = MoveTransition(0.5, enter=slide_down)\n",
        )
        ns, _ = load_ns(game_dir)
        assert ns["slide_in"].kwargs["enter"] is ns["slide_down"]


class TestLoadErrorLocations:
    def test_define_and_default_errors_carry_location(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "define bad_define = missing_name\n\ndefault bad_default = 1 / 0\n",
        )
        with pytest.raises(RuntimeError, match=r"a\.rpy:1"):
            load_ns(game_dir)
        _, errors = load_ns(game_dir, on_error="skip")
        assert [(type(item).__name__, item.source_line) for item, _ in errors] == [
            ("Define", 1),
            ("Default", 3),
        ]
        assert "a.rpy:3" in str(errors[1][1])

    def test_syntax_error_maps_to_rpy_line(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "init python:\n    x = 1\n    # comment\n\n    y = (\n    z = 1 +\n",
        )
        _, errors = load_ns(game_dir, on_error="skip")
        # Unterminated bracket: recorded as a parse error, not a crash.
        assert isinstance(errors[0][1], ParseError)

        write_rpy(game_dir, "a.rpy", "init python:\n    x = 1\n\n    y = = 1\n")
        _, errors = load_ns(game_dir, on_error="skip")
        exc = errors[0][1]
        assert isinstance(exc, SyntaxError)
        assert exc.lineno == 4

    def test_runtime_traceback_points_at_rpy_line(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "init python:\n"
            "    def ok():\n"
            "        return 1\n"
            "# column-0 comment\n"
            "\n"
            "    def boom():\n"
            "        raise KeyError('x')\n",
        )
        ns, _ = load_ns(game_dir)
        with pytest.raises(KeyError) as exc_info:
            ns["boom"]()
        frame = exc_info.traceback[-1]
        assert frame.path == game_dir / "a.rpy"
        assert frame.lineno + 1 == 7  # pytest's lineno is 0-based

    def test_parse_error_does_not_block_other_files(self, game_dir):
        write_rpy(game_dir, "a.rpy", "define X = {\n")
        write_rpy(game_dir, "b.rpy", "define Y = 1\n")
        ns, errors = load_ns(game_dir, on_error="skip")
        assert ns["Y"] == 1
        assert len(errors) == 1
        item, exc = errors[0]
        assert isinstance(exc, ParseError)
        assert (Path(item.source_file).name, item.source_line) == ("a.rpy", 1)
        with pytest.raises(ParseError):
            load_ns(game_dir)

    def test_globals_dispatch_with_two_arg_exec(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "init python:\n"
            "    def handler():\n"
            "        return 'ok'\n"
            "    def dispatch(name):\n"
            "        return globals()[name]()\n",
        )
        ns, _ = load_ns(game_dir)
        assert ns["dispatch"]("handler") == "ok"


class TestRunLabelPython:
    def test_runs_python_statements_in_order(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "label init_state:\n"
            "    $ a = 1\n"
            "    $ b = {\n"
            "        'x': a,\n"
            "    }\n"
            "    python:\n"
            "        b['y'] = 2\n"
            "    return\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        result = project.run_label_python("init_state", ns)
        assert ns["b"] == {"x": 1, "y": 2}
        assert [s.source_line for s in result.executed] == [2, 3, 6]
        assert [s.kind for s in result.skipped] == ["return"]

    def test_skips_dialogue_and_display(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            'define e = Character("Eileen")\n'
            "label scene_one:\n"
            "    scene bg room\n"
            "    show eileen happy\n"
            "    with dissolve\n"
            '    e "Hello"\n'
            "    $ seen = True\n"
            '    "Narration"\n'
            '    $ e("spoken from python")\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        result = project.run_label_python("scene_one", ns)
        assert ns["seen"] is True
        assert [s.kind for s in result.skipped] == ["scene", "show", "with", "e", "say"]
        assert len(result.executed) == 2

    def test_multiline_dialogue_hides_dollar_line(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "label a:\n"
            '    "first\n'
            "    $ x = 1\n"
            '    last"\n',
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        result = project.run_label_python("a", ns)
        assert "x" not in ns
        assert len(result.skipped) == 1

    def test_renpy_if_block_skipped(self, game_dir):
        write_rpy(
            game_dir,
            "a.rpy",
            "label a:\n"
            "    if True:\n"
            "        $ inside = 1\n"
            "    $ after = 1\n",
        )
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        result = project.run_label_python("a", ns)
        assert "inside" not in ns
        assert ns["after"] == 1
        assert [(s.kind, s.source_line) for s in result.skipped] == [("if", 2)]

    def test_jump_propagates(self, game_dir):
        write_rpy(game_dir, "a.rpy", 'label a:\n    $ renpy.jump("x")\n')
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        with pytest.raises(JumpException) as exc_info:
            project.run_label_python("a", ns)
        assert exc_info.value.target == "x"

    def test_error_names_file_and_line(self, game_dir):
        write_rpy(game_dir, "a.rpy", "label a:\n    $ ok = 1\n    $ d = {}['k']\n")
        project = load_project(game_dir)
        ns = StoreNamespace()
        project.execute_into(ns)
        with pytest.raises(RuntimeError, match=r"a\.rpy:3") as exc_info:
            project.run_label_python("a", ns)
        assert isinstance(exc_info.value.__cause__, KeyError)

    def test_unknown_label(self, game_dir):
        write_rpy(game_dir, "a.rpy", "label init_state:\n    $ a = 1\n")
        project = load_project(game_dir)
        with pytest.raises(KeyError, match="init_state"):
            project.run_label_python("init_stat", StoreNamespace())

    def test_duplicate_label(self, game_dir):
        write_rpy(game_dir, "a.rpy", "label dup:\n    $ a = 1\n")
        write_rpy(game_dir, "b.rpy", "label dup:\n    $ a = 2\n")
        project = load_project(game_dir)
        with pytest.raises(KeyError, match=r"a\.rpy:1.*b\.rpy:1"):
            project.run_label_python("dup", StoreNamespace())

    def test_label_python_not_run_by_default(self, game_dir):
        write_rpy(game_dir, "a.rpy", "label a:\n    python:\n        x = 1\n")
        ns, _ = load_ns(game_dir)
        assert "x" not in ns


class TestBoilerplateBuiltins:
    def test_stock_gui_snippet_loads_cleanly(self, game_dir):
        write_rpy(
            game_dir,
            "gui.rpy",
            "﻿init offset = -2\n"
            "init python:\n"
            "    gui.init(1920, 1080)\n"
            "define gui.text_size = 33\n"
            "define gui.button_borders = Borders(6, 6, 6, 6)\n"
            "default gui.accent = '#f00'\n"
            "default preferences.text_cps = 40\n",
        )
        write_rpy(
            game_dir,
            "options.rpy",
            'define config.name = _("Forest\'s Bane")\n'
            "define gui.about = _p(\"\"\"\n"
            "    A game.\n"
            "\"\"\")\n"
            "init python:\n"
            "    build.classify('**~', None)\n"
            "    config.character_id_prefixes.append('namebox')\n"
            "    config.overlay_screens.append('quick_menu')\n"
            "    style.default.font = 'x.ttf'\n",
        )
        ns, errors = load_ns(game_dir, on_error="skip")
        assert errors == []
        assert ns["config"].name == "Forest's Bane"
        assert ns["gui"].text_size == 33
        assert ns["gui"].button_borders.args == (6, 6, 6, 6)
        assert ns["gui"].accent == "#f00"
        assert ns["gui"].about == "A game."
        assert ns["preferences"].text_cps == 40
        assert ns["config"].overlay_screens == ["quick_menu"]
        assert ns["build"].classify._calls

        ns2, _ = load_ns(game_dir)
        assert ns2["config"].overlay_screens == ["quick_menu"]
        assert ns2["gui"] is not ns["gui"]

    def test_undefined_name_still_raises(self, game_dir):
        write_rpy(game_dir, "a.rpy", "init python:\n    totally_undefined()\n")
        with pytest.raises(RuntimeError, match=r"a\.rpy:1.*totally_undefined"):
            load_ns(game_dir)

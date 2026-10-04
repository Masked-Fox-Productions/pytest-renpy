"""Tests for pytest-renpy fixtures."""

import textwrap
from pathlib import Path


def test_renpy_game_provides_store(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "script.rpy").write_text(
        "init python:\n    x = 42\n", encoding="utf-8"
    )
    pytester.makepyfile(
        """
        def test_store_has_x(renpy_game):
            assert renpy_game.store["x"] == 42
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=1)


def test_renpy_mock_resets_between_tests(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "script.rpy").write_text(
        textwrap.dedent("""\
            init python:
                def do_jump():
                    renpy.jump("target")
        """),
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
        import pytest
        from pytest_renpy import JumpException

        def test_first(renpy_game):
            with pytest.raises(JumpException):
                renpy_game.store.do_jump()
            assert len(renpy_game.mock.jumps) == 1

        def test_second(renpy_game):
            assert len(renpy_game.mock.jumps) == 0
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=2)


def test_renpy_store_isolated_between_tests(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "script.rpy").write_text(
        "default counter = 0\n", encoding="utf-8"
    )
    pytester.makepyfile(
        """
        def test_mutate(renpy_store):
            renpy_store["counter"] = 999

        def test_fresh(renpy_store):
            assert renpy_store["counter"] == 0
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=2)


def test_renpy_game_has_labels(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "script.rpy").write_text(
        "label start:\n    pass\n\nlabel ending:\n    pass\n",
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
        def test_labels(renpy_game):
            label_names = [l.name for l in renpy_game.labels]
            assert "start" in label_names
            assert "ending" in label_names
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=1)


def test_defaults_to_current_dir(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "script.rpy").write_text(
        "init python:\n    x = 1\n", encoding="utf-8"
    )
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            assert renpy_game.store["x"] == 1
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def test_nonexistent_project_dir(pytester):
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            pass
        """
    )
    result = pytester.runpytest("--renpy-project=/nonexistent/path")
    result.assert_outcomes(errors=1)


def test_project_without_game_subdir(pytester):
    (pytester.path / "script.rpy").write_text(
        "init python:\n    x = 99\n", encoding="utf-8"
    )
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            assert renpy_game.store["x"] == 99
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=1)


def test_renpy_mock_fixture_standalone(pytester):
    pytester.makepyfile(
        """
        def test_mock(renpy_mock):
            assert renpy_mock.jumps == []
            assert renpy_mock.quit_called is False
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


def _broken_project(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "good.rpy").write_text("init python:\n    x = 42\n", encoding="utf-8")
    (game_dir / "broken.rpy").write_text(
        "init python:\n    y = undefined_name\n", encoding="utf-8"
    )
    return game_dir


def test_on_error_skip_via_ini(pytester):
    _broken_project(pytester)
    pytester.makeini("[pytest]\nrenpy_on_error = skip\n")
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            assert renpy_game.store["x"] == 42
            assert len(renpy_game.load_errors) == 1
            item, exc = renpy_game.load_errors[0]
            assert item.source_file.endswith("broken.rpy")
            assert "broken.rpy:1" in str(exc)
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=1)


def test_on_error_defaults_to_raise(pytester):
    _broken_project(pytester)
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            pass
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*broken.rpy:1*"])


def test_on_error_cli_overrides_ini(pytester):
    _broken_project(pytester)
    pytester.makeini("[pytest]\nrenpy_on_error = raise\n")
    pytester.makepyfile(
        """
        def test_it(renpy_load_errors, renpy_store):
            assert len(renpy_load_errors) == 1
        """
    )
    result = pytester.runpytest(
        f"--renpy-project={pytester.path}", "--renpy-on-error=skip"
    )
    result.assert_outcomes(passed=1)


def test_parse_error_flows_through_load_errors(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "a.rpy").write_text("define X = {\n", encoding="utf-8")
    (game_dir / "b.rpy").write_text("define Y = 1\n", encoding="utf-8")
    pytester.makepyfile(
        """
        from pytest_renpy.rpy_parser import ParseError

        def test_first(renpy_game):
            assert renpy_game.store["Y"] == 1
            [(item, exc)] = renpy_game.load_errors
            assert isinstance(exc, ParseError)
            assert item.source_file.endswith("a.rpy") and item.source_line == 1

        def test_second(renpy_game):
            assert len(renpy_game.load_errors) == 1
        """
    )
    result = pytester.runpytest(
        f"--renpy-project={pytester.path}", "--renpy-on-error=skip"
    )
    result.assert_outcomes(passed=2)

    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(errors=2)
    result.stdout.fnmatch_lines(["*ParseError*a.rpy:1*"])


def test_forbidden_default_in_load_errors(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "a.rpy").write_text("default config.x = 1\n", encoding="utf-8")
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            [(item, exc)] = renpy_game.load_errors
            assert "a.rpy:1" in str(exc)
        """
    )
    result = pytester.runpytest(
        f"--renpy-project={pytester.path}", "--renpy-on-error=skip"
    )
    result.assert_outcomes(passed=1)


def test_invalid_on_error_ini(pytester):
    pytester.mkdir("game")
    pytester.makeini("[pytest]\nrenpy_on_error = ignore\n")
    pytester.makepyfile("def test_it(renpy_store): pass")
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*renpy_on_error must be*"])


def test_run_label_python_populates_store(pytester):
    game_dir = pytester.mkdir("game")
    (game_dir / "state.rpy").write_text(
        textwrap.dedent("""\
            label init_state:
                $ inventory = []
                python:
                    inventory.append("sword")
                "You find a sword."
                return
        """),
        encoding="utf-8",
    )
    pytester.makepyfile(
        """
        def test_it(renpy_game):
            assert "inventory" not in renpy_game.store
            result = renpy_game.run_label_python("init_state")
            assert renpy_game.store["inventory"] == ["sword"]
            assert [s.kind for s in result.skipped] == ["say", "return"]
        """
    )
    result = pytester.runpytest(f"--renpy-project={pytester.path}")
    result.assert_outcomes(passed=1)

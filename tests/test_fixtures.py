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

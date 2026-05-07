"""Tests for plugin registration and option handling."""


def test_plugin_loads(pytester):
    pytester.makeconftest("")
    result = pytester.runpytest("--co")
    result.ret == 0


def test_renpy_project_option_recognized(pytester):
    pytester.makepyfile("def test_placeholder(): pass")
    result = pytester.runpytest("--renpy-project=.")
    assert result.ret == 0


def test_renpy_project_defaults_to_current_dir(pytester):
    pytester.makeconftest("")
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(["*--renpy-project*"])


def test_renpy_marker_registered(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.renpy
        def test_marked():
            pass
        """
    )
    result = pytester.runpytest("--strict-markers")
    assert result.ret == 0


def test_exception_types_importable():
    from pytest_renpy import (
        CallException,
        JumpException,
        QuitException,
        ReturnException,
    )

    exc = JumpException("target")
    assert exc.target == "target"

    exc = CallException("label")
    assert exc.target == "label"

    assert ReturnException()
    assert QuitException()

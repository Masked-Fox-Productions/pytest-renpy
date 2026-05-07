"""Proof-of-concept test configuration for terminalgame.

These tests demonstrate pytest-renpy against a real Ren'Py project.
terminalgame has a Python 3.12 syntax error in display.rpy
(global declaration after assignment), so we use on_error="skip"
to load all other init blocks.
"""

from pathlib import Path

import pytest

from pytest_renpy.loader import load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace

TERMINALGAME_DIR = Path("/projects/xander/terminalgame/game")


def pytest_collection_modifyitems(config, items):
    if not TERMINALGAME_DIR.exists():
        skip = pytest.mark.skip(reason="terminalgame not available")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def terminalgame_project():
    return load_project(TERMINALGAME_DIR)


@pytest.fixture
def game(terminalgame_project):
    ns = StoreNamespace()
    mock = create_mock()
    errors = terminalgame_project.execute_into(ns, mock_renpy=mock, on_error="skip")
    return ns, mock, errors

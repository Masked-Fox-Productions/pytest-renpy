"""Layer 1 test configuration for Forest's Bane.

A roguelike survival game whose logic lives in `init python` blocks nested
inside labels (`label init_utils:` in utils.rpy), multi-line data tables
(`CHARACTER_DETAILS`, `WEAPONS`, `item_library`), and label-built state
(`label init_board_dicts:`). Loads with on_error="skip" so tests can assert
on exactly which items failed.
"""

import os
from pathlib import Path

import pytest

from pytest_renpy.loader import load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace

GAME_DIR = Path(
    os.environ.get("RENPY_PROJECT", "/projects/xander/forests_bane")
) / "game"

HERE = Path(__file__).parent


def pytest_collection_modifyitems(config, items):
    if not GAME_DIR.exists():
        skip = pytest.mark.skip(reason="forests_bane project not available")
        for item in items:
            if HERE in Path(item.fspath).parents:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def game_dir():
    return GAME_DIR


@pytest.fixture(scope="session")
def project():
    return load_project(GAME_DIR)


@pytest.fixture
def game(project):
    ns = StoreNamespace()
    mock = create_mock()
    errors = project.execute_into(ns, mock_renpy=mock, on_error="skip")
    return ns, mock, errors

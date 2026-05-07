"""Test configuration for Minimum Viable RPG.

An RPG with locations, monsters, items, and combat. Most game logic
lives in label python: blocks (Layer 2), but init python: provides
location constants, the get_base_location factory, and credits.
Character defines use Transform for positioning.
"""

from pathlib import Path

import pytest

from pytest_renpy.loader import load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace

GAME_DIR = Path("/projects/masked_fox/minimum-viable-rpg-renpy/game")


def pytest_collection_modifyitems(config, items):
    if not GAME_DIR.exists():
        skip = pytest.mark.skip(reason="minimum-viable-rpg project not available")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def project():
    return load_project(GAME_DIR)


@pytest.fixture
def game(project):
    ns = StoreNamespace()
    mock = create_mock()
    errors = project.execute_into(ns, mock_renpy=mock, on_error="skip")
    return ns, mock, errors

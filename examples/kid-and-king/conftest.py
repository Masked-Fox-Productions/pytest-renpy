"""Test configuration for The Kid and the King of Chicago.

A visual novel with a book-recommendation mechanic. Game logic is mostly
in utils.py (imported via `from utils import *` in init python), with
define/default statements setting up characters, game state, and book data.
"""

from pathlib import Path

import pytest

from pytest_renpy.loader import load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace

GAME_DIR = Path("/projects/masked_fox/the-kid-and-the-king-of-chicago/game")


def pytest_collection_modifyitems(config, items):
    if not GAME_DIR.exists():
        skip = pytest.mark.skip(reason="kid-and-king project not available")
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

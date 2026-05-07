"""pytest-renpy fixtures for testing Ren'Py game logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pytest_renpy.loader import ProjectData, load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace


@dataclass
class RenpyGame:
    """Convenience object combining store, mock, and label metadata."""

    store: StoreNamespace
    mock: object
    labels: list


def _resolve_game_dir(project_path: Path) -> Path:
    """Find the game directory within a project path."""
    game_subdir = project_path / "game"
    if game_subdir.is_dir():
        return game_subdir
    return project_path


@pytest.fixture(scope="session")
def renpy_project(request) -> ProjectData:
    """Session-scoped fixture: parse the Ren'Py project once."""
    project_path = Path(request.config.getoption("renpy_project")).resolve()
    if not project_path.is_dir():
        pytest.fail(f"--renpy-project path does not exist: {project_path}")

    game_dir = _resolve_game_dir(project_path)
    return load_project(game_dir)


@pytest.fixture
def renpy_mock():
    """Function-scoped fixture: fresh mock renpy instance per test."""
    return create_mock()


@pytest.fixture
def renpy_store(renpy_project, renpy_mock) -> StoreNamespace:
    """Function-scoped fixture: fresh store with game init blocks executed."""
    ns = StoreNamespace()
    renpy_project.execute_into(ns, mock_renpy=renpy_mock)
    return ns


@pytest.fixture
def renpy_game(renpy_project, renpy_store, renpy_mock) -> RenpyGame:
    """Function-scoped fixture: combined game environment for testing."""
    return RenpyGame(
        store=renpy_store,
        mock=renpy_mock,
        labels=renpy_project.labels,
    )

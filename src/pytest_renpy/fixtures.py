"""pytest-renpy fixtures for testing Ren'Py game logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pytest_renpy.loader import ProjectData, load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace
from pytest_renpy.engine.runner import RenpyEngine


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


# --- Layer 2 fixtures ---


@pytest.fixture
def renpy_engine(request) -> RenpyEngine:
    """Function-scoped fixture: fresh headless Ren'Py engine per test.

    Requires --renpy-sdk and --renpy-project to be set.
    Skips if --renpy-sdk is not provided.
    """
    sdk_path = request.config.getoption("renpy_sdk")
    if sdk_path is None:
        pytest.skip("--renpy-sdk required for integration tests")

    sdk = Path(sdk_path).resolve()
    if not sdk.is_dir():
        pytest.exit(f"Ren'Py SDK not found at {sdk}")

    project_path = Path(request.config.getoption("renpy_project")).resolve()
    engine = RenpyEngine(sdk, project_path, timeout=15)
    engine.start()
    yield engine
    engine.stop()


@pytest.fixture
def renpy_session(renpy_engine) -> RenpyEngine:
    """Function-scoped fixture: convenience alias for renpy_engine.

    This is the primary fixture test authors should use for Layer 2 tests.
    """
    return renpy_engine

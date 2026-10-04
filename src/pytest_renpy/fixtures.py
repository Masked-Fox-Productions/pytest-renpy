"""pytest-renpy fixtures for testing Ren'Py game logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pytest_renpy.loader import LabelRunResult, ProjectData, load_project
from pytest_renpy.mock_renpy import create_mock
from pytest_renpy.mock_renpy.store import StoreNamespace
from pytest_renpy.engine.runner import RenpyEngine
from pytest_renpy.sdk import discover_project, discover_sdk


@dataclass
class RenpyGame:
    """Convenience object combining store, mock, and label metadata."""

    store: StoreNamespace
    mock: object
    labels: list
    project: ProjectData | None = None
    load_errors: list = field(default_factory=list)

    def run_label_python(self, name: str) -> LabelRunResult:
        """Run label ``name``'s Python statements against this game's store."""
        if self.project is None:
            raise RuntimeError("RenpyGame has no project; build it via the renpy_game fixture")
        return self.project.run_label_python(name, self.store)


def _on_error_mode(config) -> str:
    mode = config.getoption("--renpy-on-error") or config.getini("renpy_on_error")
    mode = (mode or "raise").strip()
    if mode not in ("raise", "skip"):
        raise pytest.UsageError(
            f"renpy_on_error must be 'raise' or 'skip', not {mode!r}"
        )
    return mode


def _resolve_game_dir(project_path: Path) -> Path:
    """Find the game directory within a project path."""
    game_subdir = project_path / "game"
    if game_subdir.is_dir():
        return game_subdir
    return project_path


@pytest.fixture(scope="session")
def renpy_project(request) -> ProjectData:
    """Session-scoped fixture: parse the Ren'Py project once."""
    project_path = discover_project(request.config)
    if not project_path.is_dir():
        pytest.fail(f"Project path does not exist: {project_path}")

    game_dir = _resolve_game_dir(project_path)
    return load_project(game_dir)


@pytest.fixture
def renpy_mock():
    """Function-scoped fixture: fresh mock renpy instance per test."""
    return create_mock()


@pytest.fixture
def renpy_load_errors() -> list:
    """Function-scoped fixture: (item, exception) pairs skipped while loading.

    Only populated when the error mode is ``skip`` (``--renpy-on-error`` or
    the ``renpy_on_error`` ini option); in ``raise`` mode loading fails the
    test instead.
    """
    return []


@pytest.fixture
def renpy_store(request, renpy_project, renpy_mock, renpy_load_errors) -> StoreNamespace:
    """Function-scoped fixture: fresh store with game init blocks executed."""
    ns = StoreNamespace()
    renpy_load_errors.extend(
        renpy_project.execute_into(
            ns, mock_renpy=renpy_mock, on_error=_on_error_mode(request.config)
        )
    )
    return ns


@pytest.fixture
def renpy_game(renpy_project, renpy_store, renpy_mock, renpy_load_errors) -> RenpyGame:
    """Function-scoped fixture: combined game environment for testing."""
    return RenpyGame(
        store=renpy_store,
        mock=renpy_mock,
        labels=renpy_project.labels,
        project=renpy_project,
        load_errors=renpy_load_errors,
    )


# --- Layer 2 fixtures ---


@pytest.fixture
def renpy_engine(request) -> RenpyEngine:
    """Function-scoped fixture: fresh headless Ren'Py engine per test.

    Uses the 5-step SDK autodiscovery cascade. Skips if no SDK is found.
    """
    sdk = discover_sdk(request.config)
    if sdk is None:
        pytest.skip(
            "No Ren'Py SDK found. Configure via: --renpy-sdk flag, RENPY_SDK env var, "
            "renpy_sdk ini option, or install to ~/.renpy-sdk/"
        )

    project_path = discover_project(request.config)
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

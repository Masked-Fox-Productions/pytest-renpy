"""SDK discovery and validation helpers.

Implements the 5-step autodiscovery cascade for locating the Ren'Py SDK
and project path resolution for CI/environment compatibility.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest
from packaging.version import InvalidVersion, Version


def validate_sdk_path(path: Path) -> bool:
    """Check whether a path contains a valid Ren'Py SDK (has renpy.py)."""
    if not path.is_dir():
        return False
    return (path / "renpy.py").exists()


def discover_sdk(config) -> Path | None:
    """Resolve the SDK path via the 5-step autodiscovery cascade.

    Priority: --renpy-sdk flag > RENPY_SDK env var > renpy_sdk ini option
    > ~/.renpy-sdk/ well-known path > None.
    """
    # Step 1: CLI flag (highest priority, hard error if invalid)
    cli_value = config.getoption("renpy_sdk", default=None)
    if cli_value:
        sdk = Path(cli_value).resolve()
        if not validate_sdk_path(sdk):
            pytest.exit(f"--renpy-sdk path is not a valid SDK (no renpy.py): {sdk}")
        return sdk

    # Step 2: RENPY_SDK env var
    env_value = os.environ.get("RENPY_SDK")
    if env_value:
        sdk = Path(env_value).resolve()
        if validate_sdk_path(sdk):
            return sdk
        warnings.warn(
            f"RENPY_SDK={env_value} is not a valid SDK (no renpy.py); "
            f"continuing autodiscovery",
            stacklevel=2,
        )

    # Step 3: renpy_sdk ini option
    ini_value = config.getini("renpy_sdk")
    if ini_value:
        sdk = Path(ini_value).resolve()
        if validate_sdk_path(sdk):
            return sdk
        warnings.warn(
            f"renpy_sdk ini option '{ini_value}' is not a valid SDK (no renpy.py); "
            f"continuing autodiscovery",
            stacklevel=2,
        )

    # Step 4: Well-known path ~/.renpy-sdk/
    result = _scan_wellknown_path()
    if result is not None:
        if validate_sdk_path(result):
            return result
        warnings.warn(
            f"~/.renpy-sdk/ candidate '{result}' is not a valid SDK (no renpy.py)",
            stacklevel=2,
        )

    # Step 5: None
    return None


def _scan_wellknown_path() -> Path | None:
    """Scan ~/.renpy-sdk/ for the highest semver SDK directory."""
    wellknown = Path.home() / ".renpy-sdk"
    if not wellknown.is_dir():
        return None

    versions: list[tuple[Version, Path]] = []
    for entry in wellknown.iterdir():
        if not entry.is_dir():
            continue
        try:
            ver = Version(entry.name)
            versions.append((ver, entry))
        except InvalidVersion:
            continue

    if not versions:
        return None

    versions.sort(key=lambda x: x[0], reverse=True)

    if len(versions) > 1:
        selected = versions[0]
        print(
            f"Multiple SDK versions found in ~/.renpy-sdk/; using {selected[1].name}. "
            f"Pin with RENPY_SDK env var or renpy_sdk ini option."
        )

    return versions[0][1]


def discover_project(config) -> Path:
    """Resolve the project path via cascade.

    Priority: --renpy-project flag > RENPY_PROJECT env var > renpy_project ini option
    > default '.' (current directory).
    """
    # Step 1: CLI flag
    cli_value = config.getoption("renpy_project", default=None)
    if cli_value and cli_value != ".":
        return Path(cli_value).resolve()

    # Step 2: RENPY_PROJECT env var
    env_value = os.environ.get("RENPY_PROJECT")
    if env_value:
        return Path(env_value).resolve()

    # Step 3: renpy_project ini option
    ini_value = config.getini("renpy_project")
    if ini_value:
        return Path(ini_value).resolve()

    # Step 4: CLI default or cwd
    if cli_value == ".":
        return Path(".").resolve()

    return Path(".").resolve()

"""Tests for SDK autodiscovery cascade and project discovery."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from pytest_renpy.sdk import (
    _scan_wellknown_path,
    discover_project,
    discover_sdk,
    validate_sdk_path,
)


class TestValidateSdkPath:
    def test_valid_sdk(self, tmp_path):
        (tmp_path / "renpy.py").touch()
        assert validate_sdk_path(tmp_path) is True

    def test_missing_renpy_py(self, tmp_path):
        assert validate_sdk_path(tmp_path) is False

    def test_nonexistent_path(self, tmp_path):
        assert validate_sdk_path(tmp_path / "nope") is False

    def test_file_not_directory(self, tmp_path):
        f = tmp_path / "afile"
        f.touch()
        assert validate_sdk_path(f) is False

    def test_real_sdk(self):
        sdk = Path.home() / "tools" / "renpy-8.3.7-sdk"
        if not sdk.exists():
            pytest.skip("Real SDK not available")
        assert validate_sdk_path(sdk) is True


class TestDiscoverSdk:
    def _make_config(self, tmp_path, cli_sdk=None, ini_sdk=""):
        class FakeConfig:
            def getoption(self, name, default=None):
                if name == "renpy_sdk":
                    return cli_sdk
                return default

            def getini(self, name):
                if name == "renpy_sdk":
                    return ini_sdk
                return ""

        return FakeConfig()

    def test_cli_flag_takes_priority(self, tmp_path):
        sdk_dir = tmp_path / "sdk"
        sdk_dir.mkdir()
        (sdk_dir / "renpy.py").touch()
        config = self._make_config(tmp_path, cli_sdk=str(sdk_dir))
        result = discover_sdk(config)
        assert result == sdk_dir.resolve()

    def test_cli_flag_invalid_exits(self, tmp_path):
        from _pytest.outcomes import Exit

        config = self._make_config(tmp_path, cli_sdk=str(tmp_path / "bad"))
        with pytest.raises(Exit, match="not a valid SDK"):
            discover_sdk(config)

    def test_env_var_used_when_no_cli(self, tmp_path, monkeypatch):
        sdk_dir = tmp_path / "env_sdk"
        sdk_dir.mkdir()
        (sdk_dir / "renpy.py").touch()
        monkeypatch.setenv("RENPY_SDK", str(sdk_dir))
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result == sdk_dir.resolve()

    def test_env_var_invalid_warns_and_continues(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENPY_SDK", str(tmp_path / "bad"))
        config = self._make_config(tmp_path)
        with pytest.warns(UserWarning, match="not a valid SDK"):
            result = discover_sdk(config)
        assert result is None

    def test_ini_option_used_when_no_cli_or_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        sdk_dir = tmp_path / "ini_sdk"
        sdk_dir.mkdir()
        (sdk_dir / "renpy.py").touch()
        config = self._make_config(tmp_path, ini_sdk=str(sdk_dir))
        result = discover_sdk(config)
        assert result == sdk_dir.resolve()

    def test_ini_option_invalid_warns_and_continues(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        config = self._make_config(tmp_path, ini_sdk=str(tmp_path / "bad"))
        with pytest.warns(UserWarning, match="not a valid SDK"):
            result = discover_sdk(config)
        assert result is None

    def test_wellknown_path_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        sdk_dir = tmp_path / ".renpy-sdk" / "8.3.7"
        sdk_dir.mkdir(parents=True)
        (sdk_dir / "renpy.py").touch()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result == sdk_dir

    def test_wellknown_selects_highest_version(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        base = tmp_path / ".renpy-sdk"
        for ver in ("8.2.0", "8.3.7", "8.1.0"):
            d = base / ver
            d.mkdir(parents=True)
            (d / "renpy.py").touch()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result.name == "8.3.7"

    def test_wellknown_empty_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        (tmp_path / ".renpy-sdk").mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result is None

    def test_wellknown_non_semver_ignored(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        base = tmp_path / ".renpy-sdk"
        (base / "not-a-version").mkdir(parents=True)
        (base / "readme.txt").touch()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result is None

    def test_all_cascade_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result is None

    def test_nightly_version_accepted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_SDK", raising=False)
        base = tmp_path / ".renpy-sdk"
        d = base / "8.3.7.24121801"
        d.mkdir(parents=True)
        (d / "renpy.py").touch()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = self._make_config(tmp_path)
        result = discover_sdk(config)
        assert result == d


class TestScanWellknownPath:
    def test_no_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _scan_wellknown_path() is None

    def test_multiple_versions_prints_info(self, tmp_path, monkeypatch, capsys):
        base = tmp_path / ".renpy-sdk"
        for ver in ("8.2.0", "8.3.7"):
            d = base / ver
            d.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = _scan_wellknown_path()
        assert result.name == "8.3.7"
        captured = capsys.readouterr()
        assert "Multiple SDK versions" in captured.out


class TestDiscoverProject:
    def _make_config(self, cli_project=None, ini_project=""):
        class FakeConfig:
            def getoption(self, name, default=None):
                if name == "renpy_project":
                    return cli_project
                return default

            def getini(self, name):
                if name == "renpy_project":
                    return ini_project
                return ""

        return FakeConfig()

    def test_cli_flag(self, tmp_path):
        config = self._make_config(cli_project=str(tmp_path))
        assert discover_project(config) == tmp_path.resolve()

    def test_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENPY_PROJECT", str(tmp_path))
        config = self._make_config(cli_project=".")
        result = discover_project(config)
        assert result == tmp_path.resolve()

    def test_ini_option(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RENPY_PROJECT", raising=False)
        config = self._make_config(cli_project=".", ini_project=str(tmp_path))
        result = discover_project(config)
        assert result == tmp_path.resolve()

    def test_default_cwd(self, monkeypatch):
        monkeypatch.delenv("RENPY_PROJECT", raising=False)
        config = self._make_config(cli_project=".")
        result = discover_project(config)
        assert result == Path(".").resolve()

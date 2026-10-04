"""Tests for the fetch-sdk CLI subcommand."""
from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from pytest_renpy.cli import VERSION_PATTERN, _extract, fetch_sdk, main


class TestVersionPattern:
    def test_valid_3_segment(self):
        assert VERSION_PATTERN.match("8.3.7")

    def test_valid_4_segment(self):
        assert VERSION_PATTERN.match("8.3.7.23042501")

    def test_rejects_path_traversal(self):
        assert VERSION_PATTERN.match("../evil") is None

    def test_rejects_alpha(self):
        assert VERSION_PATTERN.match("abc") is None

    def test_rejects_empty(self):
        assert VERSION_PATTERN.match("") is None

    def test_rejects_spaces(self):
        assert VERSION_PATTERN.match("8.3 .7") is None


class TestFetchSdk:
    def _make_valid_tar(self, tmp_path, version="8.3.7"):
        """Create a minimal valid tar.bz2 archive with renpy.py inside."""
        archive_path = tmp_path / "sdk.tar.bz2"
        sdk_dir_name = f"renpy-{version}-sdk"
        content_dir = tmp_path / "content" / sdk_dir_name
        content_dir.mkdir(parents=True)
        (content_dir / "renpy.py").write_text("# renpy")

        with tarfile.open(archive_path, "w:bz2") as tf:
            tf.add(content_dir.parent / sdk_dir_name, arcname=sdk_dir_name)
        return str(archive_path)

    def test_invalid_version_returns_1(self, capsys):
        result = fetch_sdk("../evil")
        assert result == 1
        assert "Invalid version format" in capsys.readouterr().err

    def test_existing_valid_sdk_skips_download(self, tmp_path, monkeypatch, capsys):
        target = tmp_path / ".renpy-sdk" / "8.3.7"
        target.mkdir(parents=True)
        (target / "renpy.py").touch()
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")

        result = fetch_sdk("8.3.7")
        assert result == 0
        assert str(target) in capsys.readouterr().out

    def test_force_redownloads(self, tmp_path, monkeypatch, capsys):
        target = tmp_path / ".renpy-sdk" / "8.3.7"
        target.mkdir(parents=True)
        (target / "renpy.py").touch()
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")

        archive = self._make_valid_tar(tmp_path)
        monkeypatch.setattr("pytest_renpy.cli._download", lambda url: archive)

        result = fetch_sdk("8.3.7", force=True)
        assert result == 0
        assert (target / "renpy.py").exists()

    def test_successful_download_and_extract(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")
        archive = self._make_valid_tar(tmp_path)
        monkeypatch.setattr("pytest_renpy.cli._download", lambda url: archive)

        result = fetch_sdk("8.3.7")
        assert result == 0
        target = tmp_path / ".renpy-sdk" / "8.3.7"
        assert target.exists()
        assert (target / "renpy.py").exists()
        out = capsys.readouterr().out
        assert str(target) in out

    def test_creates_wellknown_dir(self, tmp_path, monkeypatch, capsys):
        wellknown = tmp_path / "new" / ".renpy-sdk"
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", wellknown)
        archive = self._make_valid_tar(tmp_path)
        monkeypatch.setattr("pytest_renpy.cli._download", lambda url: archive)

        result = fetch_sdk("8.3.7")
        assert result == 0
        assert wellknown.exists()

    def test_http_404_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")

        def mock_download(url):
            raise HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr("pytest_renpy.cli._download", mock_download)

        result = fetch_sdk("99.99.99")
        assert result == 1
        assert "not found" in capsys.readouterr().err

    def test_network_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")

        def mock_download(url):
            raise URLError("Connection refused")

        monkeypatch.setattr("pytest_renpy.cli._download", mock_download)

        result = fetch_sdk("8.3.7")
        assert result == 1
        assert "Network failure" in capsys.readouterr().err

    def test_timeout_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")

        def mock_download(url):
            raise TimeoutError("Download timed out")

        monkeypatch.setattr("pytest_renpy.cli._download", mock_download)

        result = fetch_sdk("8.3.7")
        assert result == 1
        assert "timed out" in capsys.readouterr().err

    def test_corrupted_archive(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", tmp_path / ".renpy-sdk")
        bad_archive = tmp_path / "bad.tar.bz2"
        bad_archive.write_bytes(b"not a tar file")

        monkeypatch.setattr("pytest_renpy.cli._download", lambda url: str(bad_archive))

        result = fetch_sdk("8.3.7")
        assert result == 1
        assert "extract" in capsys.readouterr().err.lower()

    def test_staged_install_backup_restored_on_validation_failure(
        self, tmp_path, monkeypatch, capsys
    ):
        wellknown = tmp_path / ".renpy-sdk"
        monkeypatch.setattr("pytest_renpy.cli.WELLKNOWN_DIR", wellknown)
        target = wellknown / "8.3.7"
        target.mkdir(parents=True)
        (target / "renpy.py").write_text("original")

        # Create archive without renpy.py (invalid)
        archive_path = tmp_path / "sdk.tar.bz2"
        content_dir = tmp_path / "content" / "renpy-8.3.7-sdk"
        content_dir.mkdir(parents=True)
        (content_dir / "other.py").write_text("no renpy.py here")
        with tarfile.open(archive_path, "w:bz2") as tf:
            tf.add(content_dir, arcname="renpy-8.3.7-sdk")

        monkeypatch.setattr("pytest_renpy.cli._download", lambda url: str(archive_path))

        result = fetch_sdk("8.3.7", force=True)
        assert result == 1
        # Original should still be there (backup restored)
        assert (target / "renpy.py").read_text() == "original"


class TestExtract:
    def test_tar_path_traversal_rejected(self, tmp_path):
        archive = tmp_path / "evil.tar.bz2"
        with tarfile.open(archive, "w:bz2") as tf:
            import io

            data = b"pwned"
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        dest = tmp_path / "out"
        with pytest.raises((ValueError, tarfile.OutsideDestinationError)):
            _extract(str(archive), dest, ".tar.bz2")

    def test_zip_path_traversal_rejected(self, tmp_path):
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../../../etc/passwd", "pwned")

        dest = tmp_path / "out"
        with pytest.raises(ValueError, match="Path traversal"):
            _extract(str(archive), dest, ".zip")

    def test_valid_tar_extracts(self, tmp_path):
        archive = tmp_path / "good.tar.bz2"
        content = tmp_path / "src" / "mydir"
        content.mkdir(parents=True)
        (content / "file.txt").write_text("hello")
        with tarfile.open(archive, "w:bz2") as tf:
            tf.add(content, arcname="mydir")

        dest = tmp_path / "out"
        _extract(str(archive), dest, ".tar.bz2")
        assert (dest / "mydir" / "file.txt").read_text() == "hello"

    def test_valid_zip_extracts(self, tmp_path):
        archive = tmp_path / "good.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("mydir/file.txt", "hello")

        dest = tmp_path / "out"
        _extract(str(archive), dest, ".zip")
        assert (dest / "mydir" / "file.txt").read_text() == "hello"


class TestMainEntrypoint:
    def test_no_command_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["pytest-renpy"]):
                main()
        assert exc.value.code == 1

    def test_fetch_sdk_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["pytest-renpy", "fetch-sdk", "--help"]):
                main()
        assert exc.value.code == 0

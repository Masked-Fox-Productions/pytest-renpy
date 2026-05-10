"""CLI entry point for pytest-renpy.

Provides the `pytest-renpy fetch-sdk <version>` subcommand for downloading
and caching Ren'Py SDK versions to the well-known path ~/.renpy-sdk/.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from pytest_renpy.sdk import validate_sdk_path

WELLKNOWN_DIR = Path.home() / ".renpy-sdk"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$")
DOWNLOAD_TIMEOUT = 300
MAX_DOWNLOAD_TIME = 600


def main():
    parser = argparse.ArgumentParser(prog="pytest-renpy")
    subparsers = parser.add_subparsers(dest="command")

    fetch = subparsers.add_parser("fetch-sdk", help="Download and cache a Ren'Py SDK")
    fetch.add_argument("version", help="SDK version to download (e.g., 8.3.7)")
    fetch.add_argument(
        "--force", action="store_true", help="Re-download even if already cached"
    )

    args = parser.parse_args()

    if args.command == "fetch-sdk":
        sys.exit(fetch_sdk(args.version, force=args.force))
    else:
        parser.print_help()
        sys.exit(1)


def fetch_sdk(version: str, force: bool = False) -> int:
    if not VERSION_PATTERN.match(version):
        print(
            f"Error: Invalid version format '{version}'. "
            f"Expected format: X.Y.Z or X.Y.Z.N (e.g., 8.3.7)",
            file=sys.stderr,
        )
        return 1

    target = WELLKNOWN_DIR / version

    if target.exists() and validate_sdk_path(target) and not force:
        print(str(target))
        return 0

    ext = ".zip" if sys.platform == "win32" else ".tar.bz2"
    url = f"https://www.renpy.org/dl/{version}/renpy-{version}-sdk{ext}"

    print(f"Downloading Ren'Py SDK {version} from {url}", file=sys.stderr)

    try:
        archive_path = _download(url)
    except HTTPError as e:
        if e.code == 404:
            print(
                f"Error: SDK version '{version}' not found at {url}",
                file=sys.stderr,
            )
        else:
            print(f"Error: HTTP {e.code} downloading {url}", file=sys.stderr)
        return 1
    except URLError as e:
        print(
            f"Error: Network failure downloading SDK. "
            f"Check your connection. ({e.reason})",
            file=sys.stderr,
        )
        return 1
    except TimeoutError:
        print("Error: Download timed out", file=sys.stderr)
        return 1

    WELLKNOWN_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = WELLKNOWN_DIR / f".tmp-{version}-{os.getpid()}"

    try:
        try:
            _extract(archive_path, tmp_dir, ext)
        except (tarfile.TarError, zipfile.BadZipFile, ValueError) as e:
            print(f"Error: Failed to extract archive: {e}", file=sys.stderr)
            return 1
        finally:
            os.unlink(archive_path)

        extracted_sdk = tmp_dir / f"renpy-{version}-sdk"
        if not extracted_sdk.is_dir():
            candidates = list(tmp_dir.iterdir())
            if len(candidates) == 1 and candidates[0].is_dir():
                extracted_sdk = candidates[0]
            else:
                print(
                    "Error: Unexpected archive structure after extraction",
                    file=sys.stderr,
                )
                return 1

        if not validate_sdk_path(extracted_sdk):
            print(
                "Error: Extracted SDK is invalid (no renpy.py found)",
                file=sys.stderr,
            )
            return 1

        # Staged directory replacement
        backup = None
        if target.exists():
            backup = WELLKNOWN_DIR / f".old-{version}-{os.getpid()}"
            target.rename(backup)

        try:
            extracted_sdk.rename(target)
        except OSError:
            if backup:
                backup.rename(target)
            raise

        if backup and backup.exists():
            import shutil

            shutil.rmtree(backup, ignore_errors=True)

    finally:
        if tmp_dir.exists():
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    print(str(target))
    return 0


def _download(url: str) -> str:
    """Download URL to a temp file, returning the path."""
    resp = urlopen(url, timeout=DOWNLOAD_TIMEOUT)  # noqa: S310
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    start = time.time()

    fd, path = tempfile.mkstemp(suffix=".download")
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                if time.time() - start > MAX_DOWNLOAD_TIME:
                    raise TimeoutError("Download exceeded maximum time")
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(
                        f"\r  {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB ({pct}%)",
                        end="",
                        file=sys.stderr,
                    )
        if total:
            print(file=sys.stderr)
    except Exception:
        os.unlink(path)
        raise

    return path


def _extract(archive_path: str, dest: Path, ext: str) -> None:
    """Extract archive to dest, with path traversal protection."""
    dest.mkdir(parents=True, exist_ok=True)

    if ext == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                if os.path.isabs(info.filename) or ".." in info.filename.split("/"):
                    raise ValueError(
                        f"Path traversal detected in archive: {info.filename}"
                    )
            zf.extractall(dest)
    else:
        with tarfile.open(archive_path, "r:bz2") as tf:
            if sys.version_info >= (3, 12):
                tf.extractall(dest, filter="data")
            else:
                for member in tf.getmembers():
                    if os.path.isabs(member.name) or ".." in member.name.split("/"):
                        raise ValueError(
                            f"Path traversal detected in archive: {member.name}"
                        )
                tf.extractall(dest)


if __name__ == "__main__":
    main()

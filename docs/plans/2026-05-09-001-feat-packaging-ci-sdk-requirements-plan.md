---
title: "feat: PyPI packaging, SDK autodiscovery, fetch-sdk CLI, and CI pipeline"
type: feat
status: active
date: 2026-05-09
origin: docs/brainstorms/2026-05-09-packaging-ci-sdk-requirements.md
deepened: 2026-05-09
---

# PyPI Packaging, SDK Autodiscovery, and CI Pipeline

## Overview

Add the three features needed for public release: a 5-step SDK autodiscovery cascade so users rarely need `--renpy-sdk`, a `pytest-renpy fetch-sdk` CLI subcommand that downloads and caches SDK versions, and CI workflows for automated testing and PyPI publishing. These form a dependency chain — autodiscovery conventions inform fetch-sdk's install location, and fetch-sdk enables Layer 2 CI.

## Problem Frame

pytest-renpy has 131 tests across 4 example games but no path to distribution. Users cannot `pip install` it. SDK configuration requires `--renpy-sdk` on every invocation. There is no CI. These gaps block public release and adoption. (see origin: `docs/brainstorms/2026-05-09-packaging-ci-sdk-requirements.md`)

## Requirements Trace

**PyPI Publishing**

- R1. `publish.yml` triggers on `v*` tag push, builds with hatchling, publishes to PyPI via OIDC Trusted Publishers
- R2. Tag-version / `pyproject.toml`-version mismatch fails the workflow
- R3. `publish.yml` runs Layer 1 tests as a prerequisite job

**SDK Autodiscovery**

- R4. SDK path resolution: `--renpy-sdk` → `RENPY_SDK` env var → `renpy_sdk` ini option → `~/.renpy-sdk/` well-known path → `None`
- R5. Register `renpy_sdk` as a pytest ini option via `parser.addini()`
- R6. `~/.renpy-sdk/` scanning selects highest semver; empty → `None`
- R7. `None` SDK → Layer 2 tests skip gracefully; Layer 1 unaffected
- R8. Non-`None` SDK path validated for expected structure (`renpy.py`); warn on invalid

**SDK Fetch CLI**

- R9. `pytest-renpy fetch-sdk <version>` downloads and extracts SDK to `~/.renpy-sdk/<version>/`
- R10. `fetch-sdk` prints installed SDK path to stdout on success
- R11. Existing valid SDK at target path → skip download (unless `--force`)
- R12. Cross-platform downloads (Linux `.tar.bz2`, macOS `.tar.bz2`, Windows `.zip`)
- R13. Non-zero exit with clear error on download failure

**CI Workflows**

- R14. `ci-layer1.yml` on push/PR to main; Layer 1 tests across Python 3.9–3.12
- R15. `ci-layer2.yml` on push/PR to main; uses `fetch-sdk` + autodiscovery
- R16. Layer 2 CI caches SDK between runs, keyed on version
- R17. Both CI workflows fail fast and report clearly

## Scope Boundaries

- No multi-SDK-version CI matrix (deferred ideation item)
- No GitHub Action packaging of `fetch-sdk` as a standalone reusable action
- No documentation site or README overhaul — minimal PyPI description only
- No changelog, release notes automation, or GitHub Release creation
- No version bumping automation — developer updates `pyproject.toml` manually
- No linting/formatting CI steps (ruff, mypy) — deferred to a separate workflow

### Deferred to Separate Tasks

- DX improvements plan Unit 4 (`docs/plans/2026-05-08-001-feat-layer2-dx-improvements-plan.md`): its 2-step SDK discovery (CLI flag → `RENPY_SDK_PATH` → skip) is extended and superseded by R4-R8's 5-step cascade, which adds ini option support, well-known path scanning, and differentiated error handling. Mark Unit 4 as superseded.
- Multi-SDK CI matrix: future enhancement once single-version CI is stable
- `--path` override for `fetch-sdk` custom install location: potential future flag for CI environments preferring `/opt/` or workspace-local paths

## Context & Research

### Relevant Code and Patterns

- `src/pytest_renpy/plugin.py` — `pytest_addoption` registers `--renpy-sdk` and `--renpy-project` CLI flags; `pytest_configure` registers markers
- `src/pytest_renpy/fixtures.py` — `renpy_engine` fixture reads `--renpy-sdk`, skips if None, calls `pytest.exit()` if directory invalid
- `src/pytest_renpy/engine/runner.py:74-76` — SDK validation: checks `renpy.py` exists in SDK path
- `pyproject.toml` — hatchling build, `pytest11` entry point for plugin registration, no `[project.scripts]` yet
- Existing SDK at `~/tools/renpy-8.3.7-sdk/` — top-level contains `renpy.py`, `renpy.sh`, `renpy.exe`, `lib/`, `renpy/`

### External References

- Ren'Py SDK download URL pattern: `https://www.renpy.org/dl/{version}/renpy-{version}-sdk.{ext}`
  - Linux/macOS: `.tar.bz2` — extracts to `renpy-{version}-sdk/` directory
  - Windows: `.zip` — same contents, different archive format
  - All archives contain the full cross-platform SDK (not per-platform builds)
  - ARM Linux variant: `renpy-{version}-sdkarm.tar.bz2` (Raspberry Pi/Chromebook)
- PyPI Trusted Publishers: OIDC-based publishing, no stored API tokens, configured per-repo on pypi.org

## Key Technical Decisions

- **Env var name `RENPY_SDK`** (not `RENPY_SDK_PATH`): Matches the CLI flag `--renpy-sdk` for consistency — users learn one name, not two conventions. Supersedes the DX improvements plan's `RENPY_SDK_PATH`.

- **stdlib `urllib.request` for downloads**: No new dependencies — keeps `dependencies = ["pytest>=7.0"]` clean. `urllib.request.urlopen` with chunked reads and explicit timeout handles the download; `tarfile` / `zipfile` for extraction. Progress indication via content-length header and periodic stderr prints.

- **Archive format selection by platform**: Linux/macOS use `.tar.bz2` (native `tarfile` support). Windows uses `.zip` (native `zipfile` support). Detection via `sys.platform`.

- **Build both sdist and wheel**: Hatchling produces both trivially. `python -m build` in the publish workflow.

- **publish.yml reuses ci-layer1.yml via `workflow_call`**: Add a `workflow_call` trigger to `ci-layer1.yml`. publish.yml calls it as a prerequisite job. Single source of truth for what constitutes a passing Layer 1 run.

- **SDK validation shared function**: Both autodiscovery (R8) and fetch-sdk (R11) need to validate SDK structure. Extract to a `_validate_sdk_path(path) -> bool` helper that checks for `renpy.py`. Single source of truth.

- **Version sorting for well-known path**: Use `packaging.version.Version` unconditionally (it's a pytest dependency via `packaging`). Select the highest version directory parseable by `packaging.version.Version`. Ren'Py uses 4-segment nightly versions (e.g., `8.3.7.24121801`) — `packaging.version.Version` handles these as PEP 440 post-release segments. The directory filter must accept these formats, not just strict 3-segment semver.

- **Multiple-version info message**: When autodiscovery selects from `~/.renpy-sdk/` with multiple versions present, print an info-level message: "Multiple SDK versions found in ~/.renpy-sdk/; using {version}. Pin with RENPY_SDK env var or renpy_sdk ini option."

## Open Questions

### Resolved During Planning

- **SDK download URL stability?** Confirmed: `https://www.renpy.org/dl/{version}/renpy-{version}-sdk.{ext}` is the stable pattern used on renpy.org. Current latest is 8.5.2. The pattern has held across versions.
- **Cross-platform or per-platform SDK?** Each archive contains the full cross-platform SDK. Different formats are for extraction convenience, not platform-specific content.
- **Tarball structure?** Archives extract to a `renpy-{version}-sdk/` top-level directory. fetch-sdk should extract and then move/rename contents to `~/.renpy-sdk/{version}/`.
- **HTTP library?** stdlib `urllib.request` — no new dependencies needed.
- **sdist and/or wheel?** Both. Hatchling handles both with `python -m build`.
- **publish.yml Layer 1 reuse?** Add `workflow_call` trigger to `ci-layer1.yml` and call it from `publish.yml`. Single source of truth for what constitutes a passing Layer 1 run.
- **CI linting tools?** Deferred — just pytest for now.
- **RENPY_SDK_PATH transition?** Clean break — no fallback. The DX improvements plan was never released, so no external users have `RENPY_SDK_PATH` set. Only `RENPY_SDK` is supported.
- **SDK validation ownership (R8 vs R11)?** Shared `_validate_sdk_path()` function used by both autodiscovery and fetch-sdk. fetch-sdk validates after extraction. Autodiscovery validates at discovery time. `--force` bypasses the skip-if-exists check, not validation.
- **`--path` override for fetch-sdk?** Deferred. The well-known path `~/.renpy-sdk/` is sufficient for initial release. CI can use `RENPY_SDK` env var to point elsewhere.
- **Cache key format for CI?** Exact SDK version string from the fetch-sdk argument (e.g., `renpy-sdk-8.3.7`).

### Deferred to Implementation

- **Exact stderr progress output format**: Whether to show bytes downloaded, percentage, or just a spinner. Depends on terminal capabilities during implementation.
- **Error message wording**: Final phrasing for download failures, version-not-found, etc. Shaped by what error responses renpy.org actually returns.
- **Checksum/hash verification for SDK downloads**: A ~200MB binary archive is downloaded and extracted with trust based solely on HTTPS. Determine whether renpy.org publishes checksums or GPG signatures. If yes, verify after download. If not, decide whether to maintain an expected-hash table in the repo for known SDK versions, or accept the HTTPS-only trust model for initial release.
- **Layer 1 vs Layer 2 test classification for examples**: Most example tests (kid-and-king, terminalgame, minimum-viable-rpg) use Layer 1 fixtures only (`load_project`, `StoreNamespace`, `create_mock`) — they don't use `RenpyEngine`. They are "Layer 1 tests requiring external game data," not "Layer 2 integration tests." If minimal game fixtures are bundled, these could run in Layer 1 CI without an SDK, significantly increasing CI coverage.

## Output Structure

```
src/pytest_renpy/
├── cli.py                    # NEW: CLI entry point (fetch-sdk subcommand)
├── sdk.py                    # NEW: SDK discovery + validation helpers
├── plugin.py                 # MODIFIED: add ini option registration
├── fixtures.py               # MODIFIED: use sdk.py discovery cascade
└── engine/
    └── runner.py             # MODIFIED: use sdk.py validation helper

.github/
├── dependabot.yml              # NEW: Dependabot config for Actions SHA pins
└── workflows/
    ├── ci-layer1.yml           # NEW: Layer 1 test workflow
    ├── ci-layer2.yml           # NEW: Layer 2 test workflow
    └── publish.yml             # NEW: PyPI publish workflow

examples/
├── ci-test-game/             # NEW: bundled minimal Ren'Py game for CI Layer 2
│   ├── game/
│   │   └── script.rpy        # Minimal game exercising label nav, vars, attributes
│   ├── conftest.py
│   └── test_ci_flow.py
├── kid-and-king/conftest.py  # MODIFIED: remove hardcoded paths, use fixtures
├── forests-bane/test_bekri_flow.py  # MODIFIED: remove hardcoded paths, use fixtures
├── terminalgame/conftest.py  # MODIFIED: remove hardcoded paths, use fixtures
├── terminalgame/test_terminalgame_flow.py  # MODIFIED
├── minimum-viable-rpg/conftest.py  # MODIFIED: remove hardcoded paths, use fixtures
└── minimum-viable-rpg/test_rpg_flow.py  # MODIFIED

tests/
├── test_sdk_discovery.py     # NEW: autodiscovery + project discovery unit tests
├── test_cli_fetch_sdk.py     # NEW: fetch-sdk CLI tests (mocked unit + opt-in integration)
├── test_engine.py            # MODIFIED: use renpy_engine fixture instead of hardcoded SDK path
└── ...
```

## Implementation Units

- [ ] **Unit 1: SDK Discovery and Validation Module**

**Goal:** Extract SDK path resolution into a dedicated module with the 5-step autodiscovery cascade. Register the `renpy_sdk` ini option. Update the `renpy_engine` fixture to use the new discovery.

**Requirements:** R4, R5, R6, R7, R8

**Dependencies:** None

**Files:**
- Create: `src/pytest_renpy/sdk.py`
- Modify: `src/pytest_renpy/plugin.py`
- Modify: `src/pytest_renpy/fixtures.py`
- Modify: `src/pytest_renpy/engine/runner.py`
- Modify: `tests/test_engine.py`
- Test: `tests/test_sdk_discovery.py`

**Approach:**

`sdk.py` — new module containing:
- `validate_sdk_path(path: Path) -> bool`: checks `renpy.py` exists at path. Returns bool. Used by autodiscovery, fetch-sdk, and runner.
- `discover_sdk(config) -> Path | None`: implements the 5-step cascade:
  1. `config.getoption("renpy_sdk")` — CLI flag (highest priority)
  2. `os.environ.get("RENPY_SDK")` — env var
  3. `config.getini("renpy_sdk")` — ini option from pyproject.toml/pytest.ini
  4. `_scan_wellknown_path()` — scans `~/.renpy-sdk/`, selects highest semver
  5. Returns `None`
- `_scan_wellknown_path() -> Path | None`: lists `~/.renpy-sdk/` subdirectories, filters to directories parseable by `packaging.version.Version`, sorts descending, returns first matching path. Does not validate SDK structure — that is `discover_sdk`'s responsibility. Prints info message when multiple versions found.
- `discover_project(config) -> Path`: implements project path resolution: `config.getoption("renpy_project")` (if not default `.`) → `os.environ.get("RENPY_PROJECT")` → `config.getini("renpy_project")` → default `.` (current directory). Returns resolved `Path`. This parallels the SDK cascade but is simpler — no validation or well-known path needed.
- Validation order: `discover_sdk` receives a candidate path from each cascade step, validates it via `validate_sdk_path` before returning. If validation fails, behavior depends on the source:
- Cascade validation rules differ by source:
  - **Step 1 (CLI flag):** If provided but invalid, raise `pytest.exit()` — the user's explicit intent was unambiguous, silently falling through would be a regression from current behavior.
  - **Steps 2-4 (env var, ini, well-known path):** If path exists but `validate_sdk_path` fails, emit `warnings.warn()` and continue to next cascade step (don't hard-fail on a bad env var when ini option might be valid).

`plugin.py` — add `parser.addini("renpy_sdk", help="...", type="string", default=None)` and `parser.addini("renpy_project", help="...", type="string", default=None)` in `pytest_addoption`. Note: pytest `getini()` may return empty string for unset string options — discovery functions must check for falsy values (not just `is not None`) at the ini step. The `getoption`/`getini` namespaces are separate in pytest, so ini names don't conflict with CLI flags.

`fixtures.py` — replace direct `getoption("renpy_sdk")` with `discover_sdk(request.config)`. If returns `None`, `pytest.skip()`. Otherwise proceed directly — `discover_sdk` already validates all returned paths. Similarly, replace direct `getoption("renpy_project")` in `renpy_project` fixture with `discover_project(request.config)`, which implements: `--renpy-project` CLI flag → `RENPY_PROJECT` env var → `renpy_project` ini option → default `.` (current directory). This makes project path configurable via environment for CI without CLI flags.

`runner.py` — replace inline `renpy.py` check with `from pytest_renpy.sdk import validate_sdk_path`. Keep the `EngineError` raise — runner validates at start time as a hard error.

`tests/test_engine.py` — remove hardcoded `SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))` and `requires_sdk` skip marker. Replace direct `RenpyEngine(SDK_PATH, ...)` construction with the `renpy_engine` fixture from Unit 1's updated `fixtures.py`. Tests will autodiscover via the cascade and skip when no SDK is available, making them CI-compatible after `fetch-sdk` populates `~/.renpy-sdk/`. Also update `FIXTURE_GAME` to reference a path discoverable via `--renpy-project` or the bundled `examples/ci-test-game/` from Unit 4.

**Patterns to follow:**
- Existing `pytest_addoption` group pattern in `plugin.py`
- Existing `renpy_engine` fixture structure in `fixtures.py`
- Existing `renpy.py` validation in `runner.py:74-76`

**Test scenarios:**
- Happy path: CLI flag `--renpy-sdk` set → discovery returns that path, ignoring env var and ini
- Happy path: No CLI flag, `RENPY_SDK` env var set → discovery returns env var path
- Happy path: No CLI flag, no env var, `renpy_sdk` ini option set → discovery returns ini path
- Happy path: No CLI/env/ini, `~/.renpy-sdk/8.3.7/` exists with valid SDK → discovery returns that path
- Happy path: Multiple versions in `~/.renpy-sdk/` (8.2.0, 8.3.7) → selects 8.3.7 (highest semver)
- Edge case: `~/.renpy-sdk/` exists but is empty → returns `None`
- Edge case: `~/.renpy-sdk/` contains non-semver directory names → ignored
- Error path: CLI flag `--renpy-sdk` points to invalid path (no `renpy.py`) → hard error via `pytest.exit()`, does NOT fall through to env var
- Edge case: `RENPY_SDK` env var points to invalid path → warns, continues to ini option
- Edge case: All cascade steps return None → `None` returned, fixture skips test
- Error path: Path exists as a file, not directory → handled gracefully
- Integration: `validate_sdk_path` returns True for the real SDK at `~/tools/renpy-8.3.7-sdk/`
- Happy path: `--renpy-project` CLI flag set → `discover_project` returns that path
- Happy path: No CLI override, `RENPY_PROJECT` env var set → `discover_project` returns env var path
- Happy path: No CLI/env, `renpy_project` ini option set → `discover_project` returns ini path
- Edge case: No CLI/env/ini → `discover_project` returns `.` (current directory)

**Verification:**
- `renpy_engine` fixture works with `RENPY_SDK` env var instead of `--renpy-sdk` flag
- `renpy_engine` fixture works with `renpy_sdk` in `pyproject.toml` `[tool.pytest.ini_options]`
- Without any SDK configuration, Layer 2 tests skip with a helpful message listing all options
- Layer 1 tests are completely unaffected by autodiscovery changes
- Unit 4 in `docs/plans/2026-05-08-001-feat-layer2-dx-improvements-plan.md` is marked as superseded by this work's 5-step cascade

---

- [ ] **Unit 2: CLI Entry Point and fetch-sdk Subcommand**

**Goal:** Add a `pytest-renpy` CLI with a `fetch-sdk` subcommand that downloads and extracts Ren'Py SDK versions to the well-known path.

**Requirements:** R9, R10, R11, R12, R13

**Dependencies:** Unit 1 (uses `validate_sdk_path` from `sdk.py`)

**Files:**
- Create: `src/pytest_renpy/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_fetch_sdk.py`

**Approach:**

`pyproject.toml` — add `[project.scripts]` section:
```
[project.scripts]
pytest-renpy = "pytest_renpy.cli:main"
```

`cli.py` — new module containing:
- `main()`: argparse-based CLI entry point. Dispatches to subcommands.
- `fetch_sdk(version: str, force: bool = False)`: core fetch logic:
  1. Validate version string against `r'^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$'` — reject anything else with a clear error. This eliminates path traversal (`../`) and URL injection vectors.
  2. Compute target path: `~/.renpy-sdk/{version}/`
  2. If target exists and valid and not `--force`: print path to stdout, exit 0 (R11)
  3. Determine archive URL: `https://www.renpy.org/dl/{version}/renpy-{version}-sdk.{ext}`
     - `sys.platform == "win32"` → `.zip`
     - Otherwise → `.tar.bz2`
  4. Download to a temporary file using `urllib.request.urlopen(url, timeout=300)` with chunked reads (not `urlretrieve`, which lacks timeout support). Track total elapsed time and abort if download exceeds 600 seconds — the socket timeout only catches idle connections, not slow-drip transfers.
  5. Extract archive to a temporary sibling directory (`~/.renpy-sdk/.tmp-{version}-{pid}/`). Before extraction, validate archive member paths: reject any member with absolute paths or `..` components to prevent path traversal (zip-slip). For Python 3.12+, use `tarfile.data_filter`; for 3.9-3.11, manually check each `TarInfo.name` / `ZipInfo.filename`. Contents will be in a `renpy-{version}-sdk/` subdirectory.
  6. Validate extracted contents with `validate_sdk_path()` before moving into place.
  7. Staged directory replacement: if target `~/.renpy-sdk/{version}/` already exists (e.g., `--force` or prior corrupt install), rename it to `~/.renpy-sdk/.old-{version}-{pid}/` as a backup; then rename the temp directory to `~/.renpy-sdk/{version}/`. On success, delete the backup. On failure at any step, restore the backup if it exists and clean up the temp directory. This avoids the non-atomic case where `shutil.rmtree` + `rename` leaves no SDK if the rename fails.
  8. Print path to stdout (R10)
- Error handling (R13):
  - `urllib.error.HTTPError` (e.g., 404 for invalid version) → clear message naming the version and URL
  - `urllib.error.URLError` (network failure) → clear message suggesting checking connectivity
  - Extraction failure → clear message
  - All errors → non-zero exit code
- Progress: print download status to stderr so stdout remains clean for path capture (`RENPY_SDK=$(pytest-renpy fetch-sdk 8.3.7)`)

Argparse structure:
- `pytest-renpy fetch-sdk <version>` — positional version argument
- `pytest-renpy fetch-sdk --force <version>` — re-download even if exists

**Patterns to follow:**
- `validate_sdk_path` from `sdk.py` (Unit 1)
- Common CLI patterns: argparse subcommands, stderr for progress, stdout for machine-readable output

**Test scenarios:**

*Unit tests (mocked, no network — always run):*
- Happy path: Mocked successful download + extraction → prints path to stdout, exit 0
- Happy path: Target directory already exists and valid, no `--force` → skips download, prints existing path
- Happy path: `--force` with existing valid directory → re-downloads (mocked)
- Edge case: `~/.renpy-sdk/` doesn't exist yet → created automatically
- Edge case: Version string validation accepts `8.3.7` and `8.3.7.23042501`, rejects `../evil`, `abc`, empty
- Error path: Mocked HTTP 404 → clear error message naming version and URL, exit 1
- Error path: Mocked network failure (URLError) → clear error message, exit 1
- Error path: Corrupted archive (use tiny invalid tar/zip fixture) → extraction fails, clean error, exit 1
- Error path: Archive with path traversal member (`../../../etc/passwd`) → rejected before extraction
- Edge case: Staged install — `--force` with existing target, backup created, new install validated, backup cleaned up
- Error path: Staged install failure — extraction succeeds but validation fails → backup restored, temp cleaned

*Integration tests (real network, opt-in via `@pytest.mark.integration` or env flag):*
- Integration: `fetch-sdk 8.3.7` downloads real archive, extracts, `validate_sdk_path` passes
- Integration: After `fetch-sdk`, autodiscovery from Unit 1 finds the installed SDK at `~/.renpy-sdk/8.3.7/`

**Verification:**
- `pip install -e .` makes `pytest-renpy` CLI available
- `pytest-renpy fetch-sdk --help` shows usage
- `pytest-renpy fetch-sdk 8.3.7` produces a valid SDK at `~/.renpy-sdk/8.3.7/`
- stdout output is just the path (capturable by shell assignment)

---

- [ ] **Unit 3: CI Layer 1 Workflow**

**Goal:** Create a GitHub Actions workflow that runs Layer 1 tests (no SDK needed) across a Python version matrix on push and PR to main.

**Requirements:** R14, R17

**Dependencies:** None (Layer 1 tests already work)

**Files:**
- Create: `.github/workflows/ci-layer1.yml`

**Approach:**
- Trigger: `push` to main, `pull_request` to main, `workflow_call` (enables reuse by `publish.yml`)
- Matrix: Python 3.9, 3.10, 3.11, 3.12
- Steps: checkout → setup-python → `pip install -e .` → `pytest tests/` (Layer 1 unit tests only; example integration tests live at `examples/` outside `tests/` and are not collected)
- `fail-fast: true` for the matrix (R17)

**Patterns to follow:**
- Standard GitHub Actions Python CI patterns
- Existing `pyproject.toml` test configuration

**Test scenarios:**

Test expectation: none — CI workflow YAML is validated by GitHub Actions at runtime. Verify by pushing a branch and confirming the workflow runs.

**Verification:**
- Workflow file is valid YAML with correct trigger events
- Matrix covers the required Python versions
- Layer 1 tests pass in CI without any SDK configuration

---

- [ ] **Unit 4: Refactor Example Tests for Fixture-Based SDK Discovery**

**Goal:** Migrate example game integration tests from hardcoded SDK/project paths to the `renpy_engine` fixture, enabling autodiscovery and CI compatibility.

**Requirements:** R15 (prerequisite — Layer 2 CI needs portable tests)

**Dependencies:** Unit 1 (autodiscovery cascade must exist)

**Files:**
- Create: `examples/ci-test-game/game/script.rpy`
- Create: `examples/ci-test-game/conftest.py`
- Create: `examples/ci-test-game/test_ci_flow.py`
- Modify: `examples/kid-and-king/conftest.py`
- Modify: `examples/kid-and-king/test_kidking_flow.py`
- Modify: `examples/forests-bane/test_bekri_flow.py`
- Modify: `examples/terminalgame/conftest.py`
- Modify: `examples/terminalgame/test_terminalgame_flow.py`
- Modify: `examples/minimum-viable-rpg/conftest.py`
- Modify: `examples/minimum-viable-rpg/test_rpg_flow.py`

**Approach:**

This unit has two separable concerns: (A) removing hardcoded SDK paths from all examples, and (B) resolving game data availability for CI.

**Part A — SDK path migration (all examples):**

Current state: Each example's `conftest.py` hardcodes `SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))` and `GAME_DIR = Path("/projects/masked_fox/...")`. Tests instantiate `RenpyEngine(SDK_PATH, PROJECT_PATH, ...)` directly. This makes them non-portable.

- Remove hardcoded `SDK_PATH` from each conftest and flow test
- Replace direct `RenpyEngine` construction with the `renpy_engine` fixture (or `renpy_session`)
- The `renpy_engine` fixture handles SDK discovery via the Unit 1 cascade — no SDK path needed in the test code

**Part B — Game data for CI:**

All four example games reference external project paths not bundled in the repo (`/projects/masked_fox/...`, `/projects/xander/...`). No `game/` subdirectory exists under any `examples/` directory. Layer 2 CI cannot run these tests without bundled game data.

Resolution: Create one minimal synthetic Ren'Py game fixture under `examples/ci-test-game/` specifically for CI. This fixture should exercise the same test patterns (label navigation, variable access, attribute checks) with minimal `.rpy` files. The existing four example directories remain as developer-facing examples that require external game projects — they are excluded from CI and their `--renpy-project` paths continue to reference external directories (but via `RENPY_PROJECT` env var or ini option, not hardcoded absolute paths).

This separates the CI testing concern from the developer example concern: CI runs `examples/ci-test-game/` with bundled data; developers run the full examples locally with their own game projects.

**Patterns to follow:**
- `renpy_engine` / `renpy_session` fixture usage pattern from `fixtures.py`
- Existing `--renpy-project` conftest override pattern

**Test scenarios:**
- Happy path: `ci-test-game` exercises label navigation, variable access, and attribute checks with the `renpy_engine` fixture
- Happy path: Example test runs with `RENPY_SDK` env var set (no `--renpy-sdk` flag)
- Happy path: Example test runs with `~/.renpy-sdk/` well-known path populated by fetch-sdk
- Happy path: Example test uses `RENPY_PROJECT` env var instead of `--renpy-project` flag
- Edge case: No SDK configured → example tests skip gracefully
- Integration: `pytest examples/ci-test-game/ --renpy-project=examples/ci-test-game` works with autodiscovery (this is the CI command)

**Verification:**
- No hardcoded absolute paths remain in any `examples/` test files
- `examples/ci-test-game/` is fully self-contained (game data bundled in repo)
- `pytest examples/ci-test-game/ --renpy-project=examples/ci-test-game` passes with SDK available
- Developer-facing examples (`kid-and-king`, etc.) are runnable with SDK autodiscovery + external game project
- All example tests skip cleanly when no SDK is available

---

- [ ] **Unit 5: CI Layer 2 Workflow**

**Goal:** Create a GitHub Actions workflow that fetches the Ren'Py SDK and runs Layer 2 integration tests with SDK caching.

**Requirements:** R15, R16, R17

**Dependencies:** Unit 2 (uses `pytest-renpy fetch-sdk`), Unit 4 (example tests must use fixtures)

**Files:**
- Create: `.github/workflows/ci-layer2.yml`

**Approach:**
- Trigger: `push` to main, `pull_request` to main
- Single Python version (3.12) — Layer 2 runs against Ren'Py's bundled Python, so the host Python version matters less
- SDK version defined as a workflow-level env var (e.g., `RENPY_SDK_VERSION: "8.3.7"`) for easy updating
- Steps:
  1. Checkout
  2. Setup Python 3.12
  3. `pip install -e .`
  4. Cache restore: `actions/cache` with key `renpy-sdk-${{ env.RENPY_SDK_VERSION }}` and path `~/.renpy-sdk/`
  5. `pytest-renpy fetch-sdk ${{ env.RENPY_SDK_VERSION }}` — skips download if cache hit (R11 + R16)
  6. Cache save (automatic with `actions/cache`)
  7. Run Layer 2 tests: `pytest tests/test_engine.py examples/ci-test-game/ --renpy-project=examples/ci-test-game` — targets only the engine test suite and the bundled CI fixture game (from Unit 4). The four developer-facing example directories (`kid-and-king`, `forests-bane`, `terminalgame`, `minimum-viable-rpg`) are excluded — they require external game projects not available in CI.
- Autodiscovery (R4) finds the SDK at `~/.renpy-sdk/{version}/` automatically — the workflow does not need to set the `RENPY_SDK` env var (the discovery env var) because the well-known path scan handles it. Note: `RENPY_SDK_VERSION` (CI config for which version to download) is distinct from `RENPY_SDK` (autodiscovery cascade step 2).
- `fail-fast: true` (R17)

**Patterns to follow:**
- `actions/cache` for large binary caching
- Standard GitHub Actions Python workflow structure

**Test scenarios:**

Test expectation: none — CI workflow YAML validated at runtime. Verify by pushing with a real SDK version.

**Verification:**
- Workflow caches SDK on first run, reuses cache on subsequent runs
- Layer 2 tests run successfully with autodiscovered SDK
- Cache key changes when SDK version env var is updated

---

- [ ] **Unit 6: PyPI Publish Workflow**

**Goal:** Create a GitHub Actions workflow that builds and publishes to PyPI when a version tag is pushed, with version validation and Layer 1 test gate.

**Requirements:** R1, R2, R3

**Dependencies:** Unit 3 (pattern reference for Layer 1 test job)

**Files:**
- Create: `.github/workflows/publish.yml`
- Create: `.github/dependabot.yml`
- Modify: `pyproject.toml` (if any classifiers or metadata need updating for PyPI)

**Approach:**
- Trigger: `push` tags matching `v*`
- Job 1 — `test`: Call `ci-layer1.yml` via `uses: ./.github/workflows/ci-layer1.yml` (R3). Single source of truth — no duplicated test definition.
- Job 2 — `publish` (needs: test):
  1. Checkout
  2. Setup Python
  3. Version validation (R2): extract tag version (`${{ github.ref_name }}` → strip `v` prefix), compare against version in `pyproject.toml` (parse with `python -c "import tomllib; ..."`). Fail if mismatch.
  4. `pip install build`
  5. `python -m build` — produces sdist and wheel
  6. Publish to PyPI using `pypa/gh-action-pypi-publish` with OIDC Trusted Publishers (R1)
- Permissions: `id-token: write` for OIDC, `contents: read`
- Pin all GitHub Actions to full commit SHA (not mutable tags) — `pypa/gh-action-pypi-publish`, `actions/checkout`, `actions/setup-python`. The publish job has `id-token: write` permission, making tag-based supply-chain attacks particularly impactful.
- `.github/dependabot.yml` — configure Dependabot for `github-actions` ecosystem updates (`schedule: weekly`). This keeps SHA pins current without manual tracking. Apply to all workflow files.

**Patterns to follow:**
- `pypa/gh-action-pypi-publish` official action
- OIDC Trusted Publisher configuration (no API tokens)

**Test scenarios:**

Test expectation: none — workflow validated by pushing a test tag. Version mismatch detection verified by the inline comparison script.

**Verification:**
- Pushing `v0.1.0` with matching `pyproject.toml` version triggers build + publish
- Pushing `v0.2.0` with `pyproject.toml` still at `0.1.0` fails with clear version mismatch error
- Layer 1 tests must pass before publish job runs

## System-Wide Impact

- **Interaction graph:** `sdk.py` becomes the central SDK resolution point. `fixtures.py`, `runner.py`, and `cli.py` all depend on it. The `plugin.py` ini registration feeds into `sdk.py`'s discovery cascade via `config.getini()`.
- **Error propagation:** Explicit CLI flag `--renpy-sdk` with invalid path is a hard error (`pytest.exit()`), preserving current behavior. Lower cascade steps (env var, ini, well-known path) with invalid paths use `warnings.warn()` and continue to next step. Runner validation (at engine start) raises `EngineError` as before. CLI errors go to stderr with non-zero exit.
- **State lifecycle risks:** `~/.renpy-sdk/` is persistent user-level state. Partial downloads could leave corrupted SDKs — fetch-sdk should extract to a temp directory first, then move atomically.
- **API surface parity:** New public surface: `pytest-renpy` CLI command, `RENPY_SDK` env var, `renpy_sdk` ini option, `~/.renpy-sdk/` well-known path, `RENPY_PROJECT` env var, `renpy_project` ini option. The existing `--renpy-sdk` and `--renpy-project` CLI flags are unchanged.
- **Unchanged invariants:** All existing pytest plugin behavior, Layer 1 fixtures, Layer 2 engine protocol, and IPC format are unchanged. The `pytest11` entry point continues to register the plugin. `--renpy-sdk` flag continues to work and takes highest priority.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Ren'Py download URL pattern changes in future versions | URL pattern confirmed stable across current versions. fetch-sdk error message on 404 names the URL so users can diagnose. |
| PyPI name `pytest-renpy` already taken | Claim the name immediately by publishing a minimal 0.0.1 before starting implementation. (see origin: Dependencies/Assumptions) |
| `~/.renpy-sdk/` partial download leaves corrupted SDK | Extract to temp directory, validate, then atomic move to target path. |
| `urllib.request` lacks progress feedback for ~200MB download | Print periodic status to stderr. Accept that stdlib download UX is basic. |
| `urllib.request` has no built-in timeout — stalled download hangs CI | Set socket timeout via `urllib.request.urlopen(url, timeout=300)` and use manual chunked download instead of `urlretrieve`. Catches hung connections in CI runners with finite job limits. |
| OIDC Trusted Publisher misconfiguration | Document the one-time pypi.org setup step. publish.yml fails clearly on auth errors. |
| `packaging.version.Version` import fails (not available) | `packaging` is a dependency of pytest, so it should always be available. Import unconditionally. |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-09-packaging-ci-sdk-requirements.md](docs/brainstorms/2026-05-09-packaging-ci-sdk-requirements.md)
- **Superseded:** [docs/plans/2026-05-08-001-feat-layer2-dx-improvements-plan.md](docs/plans/2026-05-08-001-feat-layer2-dx-improvements-plan.md) Unit 4 (SDK auto-discovery)
- Ren'Py SDK downloads: `https://www.renpy.org/latest.html`
- PyPI Trusted Publishers: `https://docs.pypi.org/trusted-publishers/`
- `pypa/gh-action-pypi-publish`: `https://github.com/pypa/gh-action-pypi-publish`

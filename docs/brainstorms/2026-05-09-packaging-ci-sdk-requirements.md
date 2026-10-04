---
date: 2026-05-09
topic: packaging-ci-sdk
---

# PyPI Packaging, SDK Autodiscovery, and CI Pipeline

## Problem Frame

pytest-renpy has a working dual-layer test framework (131 tests across 4 example games) but no path to distribution or automated validation. Users cannot `pip install` it. There is no CI. SDK configuration requires a manual `--renpy-sdk` flag on every invocation with no fallback. These three gaps block public release, adoption, and the upstream Ren'Py engagement strategy.

Three interconnected features solve this as a coherent system:

```
┌─────────────────────────────────────────────────┐
│           SDK Autodiscovery Chain (R4-R8)        │
│                                                   │
│  --renpy-sdk flag  (highest priority, explicit)   │
│       ↓                                           │
│  RENPY_SDK env var                                │
│       ↓                                           │
│  renpy_sdk ini option (pyproject.toml)            │
│       ↓                                           │
│  ~/.renpy-sdk/<version>/ (latest semver wins)     │
│       ↓                                           │
│  None → Layer 2 tests skip gracefully             │
└────────────────────┬────────────────────────────┘
                     │ uses
                     ▼
┌──────────────────────────────────────────────────┐
│        fetch-sdk CLI Subcommand (R9-R13)         │
│                                                    │
│  pytest-renpy fetch-sdk 8.3.7                      │
│    → downloads SDK tarball from renpy.org           │
│    → extracts to ~/.renpy-sdk/8.3.7/               │
│    → prints path to stdout                         │
│    → autodiscovery finds it automatically           │
└────────────────────┬───────────────────────────────┘
                     │ used by
                     ▼
┌──────────────────────────────────────────────────┐
│        CI Workflows (R1-R3, R14-R17)             │
│                                                    │
│  ci-layer1.yml  ─── push/PR → Layer 1 tests       │
│  ci-layer2.yml  ─── push/PR → fetch-sdk + tests   │
│  publish.yml    ─── v* tag  → build + PyPI publish │
└──────────────────────────────────────────────────┘
```

## Requirements

**PyPI Publishing**

- R1. A `publish.yml` workflow triggers on `v*` tag push, builds with hatchling, and publishes to PyPI using OIDC Trusted Publishers (no stored API tokens).
- R2. The workflow validates that the git tag version matches the version in `pyproject.toml` before publishing. Fail the workflow on mismatch.
- R3. The workflow runs Layer 1 tests as a prerequisite job before building/publishing.

**SDK Autodiscovery**

- R4. SDK path resolution uses a cascading chain with this priority order: `--renpy-sdk` CLI flag → `RENPY_SDK` environment variable → `renpy_sdk` pytest ini option → `~/.renpy-sdk/` well-known path → `None`.
- R5. Register `renpy_sdk` as a pytest ini option via `parser.addini()` so users can set it in `pyproject.toml [tool.pytest.ini_options]` or `pytest.ini`.
- R6. When scanning `~/.renpy-sdk/`, if multiple versions exist, select the highest semver. If no versions exist, continue to `None`.
- R7. When SDK resolves to `None`, Layer 2 tests skip gracefully (preserving current behavior). Layer 1 tests are unaffected.
- R8. When a non-`None` SDK path is resolved, validate that it contains the expected SDK structure (`renpy.py`, consistent with the existing validation in `engine/runner.py`). Warn on invalid path rather than silently proceeding.

**SDK Fetch CLI**

- R9. Add a `pytest-renpy fetch-sdk <version>` CLI subcommand that downloads and extracts a Ren'Py SDK to `~/.renpy-sdk/<version>/`. This requires adding a `[project.scripts]` entry point in `pyproject.toml` (e.g., `pytest-renpy = "pytest_renpy.cli:main"`) and a CLI argument parser module.
- R10. `fetch-sdk` prints the installed SDK path to stdout on success, enabling capture via `RENPY_SDK=$(pytest-renpy fetch-sdk 8.3.7)`.
- R11. If the requested version already exists at `~/.renpy-sdk/<version>/` with a valid SDK structure, skip the download and print the existing path. Support a `--force` flag to re-download.
- R12. `fetch-sdk` handles cross-platform SDK downloads (Linux, macOS, Windows tarballs/zips from renpy.org).
- R13. `fetch-sdk` exits non-zero with a clear error message when the download fails (network error, invalid version, unsupported platform).

**CI Workflows**

- R14. A `ci-layer1.yml` workflow runs on push and PR to main. It runs Layer 1 tests (no SDK needed) across a Python version matrix (3.9, 3.10, 3.11, 3.12).
- R15. A `ci-layer2.yml` workflow runs on push and PR to main. It uses `pytest-renpy fetch-sdk` to acquire the SDK, then relies on autodiscovery (the `~/.renpy-sdk/` well-known path) to locate the SDK for tests — no explicit `RENPY_SDK` env var capture needed.
- R16. `ci-layer2.yml` caches the downloaded SDK between runs, keyed on SDK version, to avoid re-downloading the ~200MB tarball on every run.
- R17. Both CI workflows fail fast on test failures and report results clearly.

## Success Criteria

- `pip install pytest-renpy` installs successfully from PyPI. The existing pytest11 entry point auto-registers the plugin (no code changes needed — verified via `pytest --co`).
- `pytest-renpy fetch-sdk` is available as a CLI command after install (verified via `pytest-renpy fetch-sdk --help`). This requires the new `[project.scripts]` entry point.
- A developer can clone a Ren'Py game project, run `pip install pytest-renpy && pytest-renpy fetch-sdk 8.3.7 && pytest`, and have both Layer 1 and Layer 2 tests discover the SDK automatically.
- Pushing a `v*` tag to the repo triggers an automated PyPI release with no manual steps beyond the tag push.
- Layer 1 CI runs in under 2 minutes. Layer 2 CI runs in under 5 minutes (with cached SDK).
- All three workflows are green on the current test suite before the first PyPI release.

## Scope Boundaries

- **Not in scope:** Multi-SDK-version CI matrix (deferred ideation item #7). Layer 2 CI runs against a single SDK version initially.
- **Not in scope:** GitHub Action packaging of `fetch-sdk` as a standalone reusable action. The CLI subcommand is the interface; CI workflows call it directly.
- **Not in scope:** User-facing documentation site or README overhaul (deferred ideation item #6). A minimal README update for PyPI package description is acceptable.
- **Not in scope:** Changelog, release notes automation, or GitHub Release creation. Tags trigger PyPI publish only.
- **Not in scope:** Version bumping automation. The developer manually updates `pyproject.toml` version before tagging.

## Key Decisions

- **CLI subcommand over separate Action:** Bundling `fetch-sdk` inside pytest-renpy means one `pip install` gives users everything — no separate action repo to maintain. CI workflows call the CLI directly.
- **Well-known path + stdout print:** `fetch-sdk` installs to `~/.renpy-sdk/<version>/` AND prints the path. Autodiscovery works zero-config; CI can also capture explicitly for reproducibility.
- **Latest semver wins:** When multiple SDK versions exist in `~/.renpy-sdk/`, autodiscovery picks the highest version. Users override with env var or ini option when they need a specific version.
- **Separate CI workflows:** `ci-layer1.yml` and `ci-layer2.yml` are independent. Layer 1 failures don't get muddied by SDK issues. Layer 2 failures don't block Layer 1 reporting.
- **Tag-triggered release:** `v*` tag push triggers build + publish. No GitHub Release ceremony required. Version-tag mismatch is a hard failure.
- **Autodiscovery priority order:** CLI flag wins (explicit override), then env var (CI/shell config), then ini option (project config), then well-known path (global default). This matches the specificity principle: more explicit = higher priority.
- **Env var name: `RENPY_SDK`** (not `RENPY_SDK_PATH`). Matches the CLI flag naming convention (`--renpy-sdk`). This supersedes the DX improvements plan Unit 4, which used `RENPY_SDK_PATH`.

## Dependencies / Assumptions

- **R4-R8 supersede DX improvements plan Unit 4** (`docs/plans/2026-05-08-001-feat-layer2-dx-improvements-plan.md`). That plan's Unit 4 specifies a 2-step SDK auto-discovery cascade (`--renpy-sdk` → `RENPY_SDK_PATH` → skip). This document's 5-step cascade is a strict superset. Unit 4 should be marked as absorbed by this work to avoid redundant implementation.
- PyPI Trusted Publishers requires configuring the GitHub repo as a trusted publisher on pypi.org before the first release. This is a one-time manual setup step.
- Ren'Py SDK download URLs follow the pattern `https://www.renpy.org/dl/<version>/renpy-<version>-sdk.tar.bz2` (or similar). URL format stability is assumed but should be verified during planning.
- **Prerequisite:** Claim the `pytest-renpy` package name on PyPI (publish a minimal 0.0.1 or register) before starting implementation. Name squatting risk is real and eliminates cheaply.

## Outstanding Questions

### Deferred to Planning

- [Affects R9][Needs research] What are the exact Ren'Py SDK download URL patterns for each platform (Linux, macOS, Windows)? Are there stable CDN URLs or only the main renpy.org domain?
- [Affects R12][Needs research] How does the SDK tarball structure differ across platforms? Is extraction logic platform-specific?
- [Affects R9][Technical] Should `fetch-sdk` support a `--path` override to install to a custom location instead of `~/.renpy-sdk/`? Useful for CI environments that prefer `/opt/` or workspace-local paths.
- [Affects R14][Technical] What linting/formatting tools should ci-layer1.yml include beyond pytest? (ruff, mypy, etc.)
- [Affects R1][Technical] Should `publish.yml` build both sdist and wheel, or wheel only? Hatchling supports both.

### From 2026-05-09 review

- [Affects R9][Blocking] Verify the exact Ren'Py SDK download URL patterns before planning R9-R13. URL format stability is load-bearing — the entire fetch-sdk feature, Layer 2 CI, and the flagship developer experience depend on it. Confirm whether Ren'Py distributes a single cross-platform SDK tarball or per-platform archives.
- [Affects R6][Design] Consider printing a warning when autodiscovery selects from `~/.renpy-sdk/` with multiple versions present, to avoid silently switching SDK versions across projects. Alternatively, require an explicit version specifier in ini options so the well-known path lookup is version-pinned.
- [Affects R8, R9, R11][Technical] Clarify SDK structure validation ownership. R8 validates in autodiscovery, R9 extracts in fetch-sdk, R11 checks before skipping download. Should fetch-sdk validate after extraction? If it doesn't, R11 could silently skip a corrupted SDK.
- [Affects R3, R14][Technical] Specify whether `publish.yml` reuses `ci-layer1.yml` as a reusable workflow call, runs its own copy of Layer 1 tests, or relies on GitHub Actions job dependencies.
- [Affects R9-R13][Technical] Declare whether HTTP downloads for SDK tarballs use stdlib `urllib` (limited, no progress) or add a third-party dependency like `httpx`/`requests`. Current deps are only `pytest>=7.0`.
- [Affects R16][Technical] Define the exact cache key format for SDK version in CI (e.g., exact version string from fetch-sdk argument, or a hash of the download URL).

## Next Steps

These three features form a dependency chain for implementation planning:

1. **SDK Autodiscovery** (R4-R8) — changes to `plugin.py` and `fixtures.py`. No external dependencies. Plan and implement first.
2. **SDK Fetch CLI** (R9-R13) — new CLI subcommand. Depends on autodiscovery conventions being settled. Plan and implement second.
3. **CI + PyPI Pipeline** (R1-R3, R14-R17) — GitHub Actions workflows. Depends on fetch-sdk existing for Layer 2 CI. Plan and implement third.

→ `/ce-plan` for each feature in dependency order, starting with SDK Autodiscovery.

---
date: 2026-05-08
topic: packaging-and-upstream-integration
focus: "Two initiatives: (1) clean pip install with PyPI + GitHub Actions, (2) alignment with Ren'Py upstream test harness requests"
mode: repo-grounded
---

# Ideation: pytest-renpy Packaging & Upstream Integration

## Grounding Context

### Codebase Context
- Python pytest plugin for Ren'Py visual novels with dual-layer architecture (Layer 1 mock unit tests, Layer 2 headless IPC integration tests)
- Modern pyproject.toml with hatchling build, pytest11 entry point, MIT license already configured
- No CI/CD pipeline, no GitHub Actions workflows
- 131 integration tests across 4 example games
- SDK discovery requires explicit `--renpy-sdk` CLI flag with no env var or config fallback
- No user-facing documentation beyond code-level

### External Context
- Ren'Py has 3 open issues requesting testing infrastructure (#3198, #6693, #5808) — no official solution
- Built-in `testcases` system is DSL-only, no pytest integration, no CI-friendly output
- Community tools (renutil, renkit, renconstruct) successfully distribute via PyPI — proven channel
- No pip-installable test harness exists for Ren'Py — gap is real and unoccupied
- pytest-django/flask pattern: stay independent, get endorsed, possibly transfer to pytest-dev org
- PyPI Trusted Publishers with OIDC is current best practice (no API tokens needed)
- Ren'Py distributes as SDK downloads, not pip — pytest-renpy is a dev tool (system Python)

## Ranked Ideas

### 1. PyPI Release Pipeline with Trusted Publishers
**Description:** Two-workflow GitHub Actions pipeline: (a) CI on push/PR runs Layer 1 tests and lints, (b) release-on-tag builds with hatchling and publishes to PyPI via OIDC Trusted Publishers — zero stored API tokens. pyproject.toml build config is already in place.
**Rationale:** Mechanical prerequisite for public distribution. Trusted Publishers is current PyPI best practice. Community tools prove PyPI is the accepted Ren'Py dev tool channel. Claims the `pytest-renpy` name early.
**Downsides:** Layer 2 tests can't run in basic CI without solving SDK bootstrapping. Initial CI only validates Layer 1.
**Confidence:** 95%
**Complexity:** Low
**Status:** Explored

### 2. SDK Autodiscovery Chain + pytest ini Options
**Description:** Replace mandatory `--renpy-sdk` CLI flag with cascading discovery: `RENPY_SDK` env var → `pyproject.toml [tool.pytest.ini_options]` → well-known filesystem paths → `--renpy-sdk` flag as last resort. Register `renpy_sdk` as a pytest ini option via `parser.addini()`.
**Rationale:** Single highest-friction moment in user journey. pytest-django solved this with `DJANGO_SETTINGS_MODULE`. Ini option lets game projects configure once and forget.
**Downsides:** Auto-discovery of well-known paths can be fragile across OS versions. Too-aggressive discovery might find wrong SDK version silently.
**Confidence:** 90%
**Complexity:** Low
**Status:** Explored

### 3. SDK Bootstrapping for CI (Reusable GitHub Action or CLI Command)
**Description:** Mechanism to download, extract, and cache a specific Ren'Py SDK version for CI. Either a GitHub Action (`setup-renpy-sdk`) or CLI command (`pytest-renpy fetch-sdk 8.3.7`) that downloads from renpy.org, extracts to a predictable path, and integrates with `actions/cache`. Uses the autodiscovery conventions from Idea 2 (sets `RENPY_SDK` env var).
**Rationale:** Blocking dependency for Layer 2 in CI. Every adopter faces this problem. Solving it once creates leverage for the entire community. renutil proves SDK download is programmatically feasible.
**Downsides:** SDK tarballs are ~200MB. Ren'Py download URLs aren't a stable API. Maintaining a GitHub Action is a separate maintenance surface.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Explored

### 4. Protocol-First Upstream Strategy (RenpyDriver Spec)
**Description:** Extract IPC protocol into a formal, versioned "RenpyDriver" specification. Submit as the upstream contribution with pytest-renpy as reference implementation and `_test_harness.rpy` as polyfill.
**Rationale:** Follows WebDriver/LSP playbook: define the protocol, not the tool. Ren'Py doesn't have to adopt pytest as a dependency.
**Downsides:** A spec without adoption is just a document. Requires upstream buy-in on protocol shape.
**Confidence:** 65%
**Complexity:** Medium
**Status:** Deferred

### 5. Upstream Engagement: Show, Don't Propose
**Description:** Post working demonstrations on Ren'Py issues #3198, #6693, #5808 showing pytest-renpy solving each request. Include PyPI package links, example test suites, and CI compatibility matrix.
**Rationale:** pytest-django path started with showing up with running code. Three issues represent years of demand with no response.
**Downsides:** Must be done after package is polished. Requires diplomatic framing.
**Confidence:** 85%
**Complexity:** Low
**Status:** Deferred

### 6. User-Facing Documentation with Living Example Games
**Description:** README with installation, quickstart, Layer 1 vs Layer 2 explanation, fixture reference. Structure 4 example games as graduated tutorials. CI runs every example's tests so docs never go stale.
**Rationale:** Documentation is the adoption funnel. Ren'Py community needs "copy this, run this, see this output." Content already exists in example games.
**Downsides:** Maintenance overhead. Dual-layer architecture requires careful explanation.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Deferred

### 7. CI Compatibility Matrix as Trust Signal
**Description:** Test against multiple Ren'Py SDK versions (8.1, 8.2, 8.3) and Python versions (3.9-3.12) in GitHub Actions matrix. Publish as compatibility badge.
**Rationale:** Proves to upstream that pytest-renpy tracks SDK changes. Gives game developers confidence. Catches breaking changes automatically.
**Downsides:** Older SDK versions may have incompatible internals. Increases CI time and cache storage.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Deferred

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Error message quality / structured diagnostics | Covered by existing Layer 2 DX plan |
| 2 | Record-and-replay test generation | Too expensive relative to packaging/upstream goals |
| 3 | In-engine test reporter (Godot GUT) | Violates "stay lightweight" for a pytest plugin |
| 4 | Invert runtime (pytest inside Ren'Py's Python) | Would abandon current IPC architecture |
| 5 | Build on Ren'Py's testcases DSL | Too limited for pytest-renpy's use cases |
| 6 | Embed protocol / decouple from SDK launching | Chicken-and-egg with upstream |
| 7 | Audience reframing | Strategic lens, not actionable idea |
| 8 | Contribution onboarding | Follows from docs + packaging |
| 9 | Standalone renpy-stubs package | Scope creep |
| 10 | Conformance suite / CRO pattern | Subsumed by CI matrix + engagement |
| 11 | Test scaffold generator | Premature before packaging exists |
| 12 | Plugin platform architecture | YAGNI at current stage |
| 13 | Package split (Layer 1/2 separate packages) | Optional extras achieve same without complexity |
| 14 | Target Ren'Py's Python interpreter | Harder packaging story |
| 15 | LSP capability negotiation | Premature at v0.1.0 |
| 16 | Mock surface area parity tracking | Not core to either initiative |
| 17 | Upstream-first (merge into SDK) | Too aggressive; independent path better |
| 18 | Audience of Ten (engine contributors only) | Too narrow |
| 19 | npm peer dependencies pattern | Already how it works |

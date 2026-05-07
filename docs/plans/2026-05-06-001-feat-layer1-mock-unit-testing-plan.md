---
title: "feat: Layer 1 — Mock-Based Unit Testing Plugin"
type: feat
status: active
date: 2026-05-06
origin: docs/plans/layer1-mock-unit-testing.md
deepened: 2026-05-06
---

# feat: Layer 1 — Mock-Based Unit Testing Plugin

## Overview

Build `pytest-renpy`, a pip-installable pytest plugin that extracts Python logic from `.rpy` files and runs it under a mock `renpy` namespace. Users test their game logic with standard `pytest` — no Ren'Py SDK required at test time.

## Problem Frame

Ren'Py games embed significant Python logic inside `.rpy` files (command routing, input handling, display logic, game state management). This code is untestable without the Ren'Py engine because it lives in a non-standard file format and references the `renpy` module globally. Developers cannot catch bugs like the `delete_cmd` issue (where the function ignores its `category` parameter and always operates on `'temporary_cmds'`) without manually playing through the game.

This plugin solves the extraction and mocking problems so that game Python can be tested with standard tooling.

## Requirements Trace

- R1. Parse `init python:` blocks from `.rpy` files into executable Python
- R2. Parse `define` and `default` statements into store assignments
- R3. Track label names as metadata (entry points for Layer 2)
- R4. Mock the `renpy` namespace sufficiently for game Python to execute without crashing
- R5. Replicate Ren'Py's exception-based control flow (`renpy.jump` raises `JumpException`, etc.)
- R6. Provide pytest fixtures that give each test a fresh store with game defaults loaded
- R7. Handle multi-file projects with init-priority ordering
- R8. Installable via `pip install pytest-renpy`, auto-discovered by pytest
- R9. Tests run with standard `pytest` command, no special invocation
- R10. Sub-1-second startup for a project the size of terminalgame (~13 .rpy files)

## Scope Boundaries

- No screen definitions parsing (screens are Ren'Py DSL, not Python)
- No `_ren.py` file handling (these are already importable Python — users test them directly)
- No `$` statement or `python:` block extraction from within labels (label-level code is metadata only in Layer 1)
- No `python early:` block handling (creator-defined statements require engine internals; revisit if demand emerges)

### Deferred to Layer 2

- Label-flow execution (jump/call/return navigation): Layer 2 plan
- Input simulation and tick-loop advancement: Layer 2 plan
- Headless Ren'Py engine boot and IPC: Layer 2 plan
- Screen state inspection: Layer 2 plan

## Context & Research

### Relevant Code and Patterns

The target proof-of-concept is the **terminalgame** project (`/projects/xander/terminalgame/`). Key patterns observed:

- **All testable logic is in `init python:` blocks** — functions like `game_send()`, `check_for_commands()`, `game_print()`, `does_show_character()`, `create_cmd()`, `delete_cmd()` are defined in `init python:` blocks across multiple files
- **Store is the implicit global namespace** — variables like `terminal_log`, `cmd_dict`, `typing_message`, `input_mode`, `markup_data` are bare assignments inside `init python:` blocks. Functions reference them as globals
- **`default` for persistent** — `default persistent.save_data = None` in globals.rpy
- **`define` for characters** — `define v = Character("Vince", color="#8B2A3A")` in renpy-rigging's script.rpy (not present in terminalgame but common)
- **Control flow via exceptions** — `renpy.jump()`, `renpy.call()`, `renpy.quit()` are used to transfer control. `game_send()` calls `check_for_commands()` which calls `globals()[destination](message)` then `renpy.jump("handle_tick")`
- **`renpy.pause(0.2)`** in the tick loop, **`renpy.random.randint()`** for randomness
- **`TintMatrix()` and `Transform()`** used in display.rpy for visual effects
- **`persistent`** used as attribute-access object in save_data.rpy
- **Multiple `init python:` blocks per file** — rig_scenes.rpy has three separate `init python:` blocks
- **Cross-file dependencies** — functions in keyboard.rpy call `game_print()` defined in display.rpy, using globals from globals.rpy
- **`globals()` dynamic dispatch** — `check_for_commands()` uses `globals()[destination](message)` to call functions by string name. `print_command()` uses `globals()[var_name]` for variable introspection. This pattern requires the exec namespace to be the dict returned by `globals()`

### Cross-Project Patterns (terminalgame, kid-and-king, minimum-viable-rpg)

Analysis of three Ren'Py projects of varying complexity reveals the `renpy.*` API surface the mock must cover:

- **Common across all projects:** `renpy.jump()`, `renpy.call()` for control flow; `define NAME = Character(...)` for character declarations; `default x = value` for game state
- **`import random` in `init python:`** — both kid-and-king and minimum-viable-rpg import `random` in init blocks. Standard library imports must work in exec'd code
- **`.py` file imports** — kid-and-king uses `from utils import *` in `init python:` to import a standard Python file (`game/utils.py`). This works because Ren'Py adds `game/` to `sys.path`. The loader should ensure the project's `game/` directory is on `sys.path` during exec
- **`renpy.display_menu()`** — the most commonly used `renpy.*` API in normal projects (programmatic menu construction). Not present in terminalgame but used in both other projects
- **Scene management APIs** — minimum-viable-rpg uses `renpy.scene()`, `renpy.show()`, `renpy.hide()`, `renpy.with_statement()` programmatically in Python code
- **`renpy.version()`** — called in credits `init python:` blocks in both normal projects
- **`Transform()` in `define`** — minimum-viable-rpg uses `define center_left = Transform(xalign=0.35, yalign=1.0, zoom=0.9)` at top level
- **`Character()` as injectable global** — universally used in `define` statements, must be available in the exec namespace
- **Functions in label `python:` blocks** — minimum-viable-rpg defines 18 utility functions inside `label init_utils:` / `python:` (Layer 2 territory, but the most common pattern for complex game logic)
- **`default` inside labels** — minimum-viable-rpg puts all 19 defaults inside `label start:`, not top-level (Layer 2 territory)

### External References

- No existing pytest plugin for Ren'Py exists — this is novel
- `pytest-django`, `pytest-flask` are architectural models for plugin structure
- pytest11 entry point for auto-discovery, `pytester` fixture for self-testing
- Ren'Py uses flexible indentation (any consistent indent width, not just 4 spaces)

## Key Technical Decisions

- **Parse-and-exec at test time** (not generated .py files): No files to manage, no cache invalidation complexity. The parser produces a Python code string that gets `exec()`'d into a namespace per test. Parsed output is cached at session scope for performance.

- **Exception-based control flow by default**: `renpy.jump()` raises `JumpException`, matching real Ren'Py behavior. This catches bugs where code after a jump shouldn't execute. The mock provides a `renpy.jump` that records the target AND raises. Tests catch exceptions to verify flow: `with pytest.raises(JumpException)`.

- **Store as a shared namespace object**: The store is a namespace (attribute and dict access) populated by executing parsed `init python:` blocks in priority order. Each test gets a fresh copy via function-scoped fixture. Store variables are the globals that `init python:` code assigns to.

- **`renpy.random` deterministic by default**: Seeded with 0 for reproducible tests. Configurable via the `renpy_mock` fixture.

- **Line-by-line state machine parser**: Ren'Py's `.rpy` syntax is indentation-based and regular enough that a state machine parser (not a full AST) handles the extraction cases. The parser tracks indentation depth to know when blocks end.

- **2-argument `exec(code, namespace)` form exclusively**: The namespace dict serves as both globals and locals for exec'd code. This ensures `globals()` inside exec'd code returns the namespace dict — critical for terminalgame's `globals()[destination](message)` dynamic dispatch and `globals()[var_name]` introspection. The 3-argument form `exec(code, globals_dict, locals_dict)` is explicitly rejected: it causes top-level assignments (including `def` statements) to land in `locals_dict`, making functions invisible to `globals()` calls in other exec'd blocks.

- **All init blocks share a single namespace dict**: Each `exec(block.code, namespace)` call uses the same dict, so definitions accumulate across blocks. This matches Ren'Py's actual behavior where all `init python:` code shares a single store namespace. Functions defined in one file's init block are callable by name from another file's init block via the shared dict.

- **Re-exec per test, not deep-copy**: Each test re-executes all init blocks into a fresh namespace dict. Deep-copy of a populated namespace is ruled out because copied function objects retain `__globals__` references pointing to the original namespace dict, not the copy. This means `global` declarations and `globals()` calls in copied functions would read/write the original dict, breaking test isolation. Re-exec is fast because parsed code strings are cached at session scope; only the `exec()` calls run per test.

- **hatchling build backend with src layout**: Modern Python packaging. `src/pytest_renpy/` layout with `pytest11` entry point in `pyproject.toml`.

## Open Questions

### Resolved During Planning

- **Jump handling approach?** Exception-based by default. Matches real Ren'Py. Tests use `pytest.raises(JumpException)` to verify flow targets.

- **`_ren.py` files?** Out of scope — they're already importable Python that users can test directly with standard pytest.

- **`renpy.random` handling?** Deterministic seed (0) by default. Tests can reconfigure via `renpy_mock.random.seed(N)`.

- **Namespace isolation?** Parsed code is cached at session scope. Execution into a fresh namespace happens per-test (function-scoped fixture). Each test starts with a clean store populated from `default`/`define` statements and `init python:` globals.

- **Parser scope?** `init python:` blocks, `define`, and `default` only. Labels are metadata. `$` statements and `python:` blocks inside labels are deferred to Layer 2.

- **Store reset strategy?** Re-exec per test, not deep-copy. Deep-copy breaks function `__globals__` references — copied functions would still point at the original namespace dict, making `global` declarations and `globals()` calls operate on the wrong dict. Re-exec is fast (parsed code is session-cached; only exec runs per test).

### Deferred to Implementation

- **Exact indentation detection strategy**: The parser needs to handle flexible indent widths. Implementation will determine whether to detect indent width from the first indented line or track relative depth changes.
- **`define` with init priority** (`define N x = ...`): Rare in practice (not seen in any of the three reference projects). Implementation will determine whether to handle the priority variant or treat all defines as priority 0.
- **Re-exec side effects**: Re-executing init blocks per test re-runs ALL statements including `print()` calls and any non-idempotent module-level operations. For terminalgame this is harmless (side effects are inside function bodies), but projects with module-level setup (e.g., appending to external lists, registering handlers) could see accumulated state. May need a mechanism to suppress stdout during re-exec or document this as a known limitation.
- **Testing pattern for functions that always raise**: `check_for_commands()` always ends with `renpy.jump("handle_tick")` raising `JumpException`. Tests must catch the exception before asserting on store mutations (e.g., `terminal_log`). Test examples should demonstrate this pattern clearly — wrap calls in `pytest.raises(JumpException)` and assert on state changes within the `with` block or afterward.
- **Exception propagation through `globals()` dispatch**: When `globals()[destination](message)` calls a destination function that raises (e.g., `quit_command` raises `QuitException`), execution of `check_for_commands` halts at that point. The raised exception's target comes from the destination function, not from the fallback `renpy.jump("handle_tick")`. Test authors need to understand that the exception type/target depends on which destination function is dispatched.

## Output Structure

```
pytest-renpy/
  pyproject.toml
  README.md
  src/
    pytest_renpy/
      __init__.py
      plugin.py              # pytest hooks + option registration
      rpy_parser.py           # .rpy file parser → Python code strings
      loader.py               # multi-file project loader with init ordering
      fixtures.py             # pytest fixtures (renpy_game, renpy_store, etc.)
      mock_renpy/
        __init__.py           # top-level renpy namespace mock
        store.py              # store namespace with attribute + dict access
        exports.py            # renpy.jump, renpy.call, renpy.pause, etc.
        config.py             # renpy.config mock
        persistent.py         # persistent storage mock
        display.py            # Transform, TintMatrix stubs
        random.py             # renpy.random mock (seedable)
  tests/
    conftest.py
    test_rpy_parser.py
    test_mock_renpy.py
    test_loader.py
    test_fixtures.py
    test_plugin.py            # pytester-based plugin integration tests
```

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌──────────────────────────────────────────────────────┐
│                    pytest invocation                   │
│                                                       │
│  pytest_addoption("--renpy-project", default=".")     │
│                     │                                 │
│                     ▼                                 │
│  ┌──────────────────────────────────┐                 │
│  │  rpy_parser.parse_file(path)    │ ◄── per .rpy    │
│  │  → ParsedFile(init_blocks=[...],│     file         │
│  │    defines=[...], defaults=[...],│                 │
│  │    labels=[...])                │                  │
│  └──────────────┬───────────────────┘                 │
│                 │                                     │
│                 ▼                                     │
│  ┌──────────────────────────────────┐                 │
│  │  loader.load_project(dir)       │                  │
│  │  1. Glob all .rpy files         │                  │
│  │  2. Parse each file             │                  │
│  │  3. Collect all init blocks     │                  │
│  │  4. Sort by priority            │                  │
│  │  5. Return ProjectData          │                  │
│  └──────────────┬───────────────────┘                 │
│                 │                                     │
│                 ▼                                     │
│  ┌──────────────────────────────────┐                 │
│  │  fixtures (per test):           │                  │
│  │  1. Create fresh StoreNamespace │                  │
│  │  2. Inject mock_renpy into ns   │                  │
│  │  3. Exec init blocks in order   │                  │
│  │  4. Apply define/default values │                  │
│  │  5. Yield renpy_game            │                  │
│  └──────────────────────────────────┘                 │
│                                                       │
│  Test code calls store functions directly:             │
│    renpy_game.store.game_send()                       │
│    renpy_game.store.check_for_commands("quit")        │
│    → JumpException raised → test catches + asserts    │
└───────────────────────────────────────────────────────┘
```

## Implementation Units

- [ ] **Unit 1: Package Scaffolding and Plugin Registration**

**Goal:** Create the installable package structure with a working pytest plugin entry point that registers CLI options and markers.

**Requirements:** R8, R9

**Dependencies:** None

**Files:**
- Create: `pyproject.toml`
- Create: `src/pytest_renpy/__init__.py`
- Create: `src/pytest_renpy/plugin.py`
- Test: `tests/test_plugin.py`
- Create: `tests/conftest.py`

**Approach:**
- Use hatchling build backend with `src/` layout
- Register `pytest11` entry point: `renpy = "pytest_renpy.plugin"`
- `plugin.py` implements `pytest_addoption` (adds `--renpy-project` option) and `pytest_configure` (registers `@pytest.mark.renpy` marker)
- Use `pytest_plugins = ["pytest_renpy.fixtures"]` in plugin.py to auto-expose fixtures
- `__init__.py` exports exception types (`JumpException`, `CallException`, `ReturnException`, `QuitException`) for test imports

**Patterns to follow:**
- pytest-django's plugin.py structure for entry point registration
- hatchling `[tool.hatch.build.targets.wheel] packages = ["src/pytest_renpy"]`

**Test scenarios:**
- Happy path: `pytester` test verifies plugin loads and `--renpy-project` option is recognized
- Happy path: `pytester` test verifies `@pytest.mark.renpy` marker is registered and doesn't warn
- Edge case: `--renpy-project` defaults to `"."` when not specified

**Verification:**
- `pip install -e .` succeeds
- `pytest --co` shows the plugin loaded (no import errors)
- `pytest --help` shows `--renpy-project` option

---

- [ ] **Unit 2: `.rpy` File Parser**

**Goal:** Parse individual `.rpy` files to extract `init python:` blocks, `define` statements, `default` statements, and label metadata.

**Requirements:** R1, R2, R3

**Dependencies:** Unit 1 (package structure exists)

**Files:**
- Create: `src/pytest_renpy/rpy_parser.py`
- Test: `tests/test_rpy_parser.py`

**Approach:**
- Line-by-line state machine with states: `TOPLEVEL`, `IN_INIT_PYTHON`, `IN_LABEL`, `IN_SCREEN` (skip), `IN_RENPY_BLOCK` (skip)
- Track indentation depth to detect block boundaries. Detect indent width from the first indented line of each block (don't assume 4 spaces)
- `parse_file(path) -> ParsedFile` returns a data class with:
  - `init_blocks: list[InitBlock]` — each has `priority: int`, `store_name: str | None`, `code: str`, `source_file: str`, `source_line: int`
  - `defines: list[Define]` — each has `name: str`, `expression: str`, `priority: int`
  - `defaults: list[Default]` — each has `name: str`, `expression: str`
  - `labels: list[Label]` — each has `name: str`, `source_line: int`
- Parse `init python:` → extract indented body as code string. Handle `init N python:` for priority. Handle `init python in storename:` for named stores
- Parse `define x = expr` → Define(name="x", expression="expr", priority=0). Handle `define N x = expr`
- Parse `default x = expr` → Default(name="x", expression="expr"). Handle `default persistent.x = expr`
- Parse `label name:` → Label(name="name"). Handle `label name(params):`
- Skip: `screen`, say statements, `show`, `scene`, `menu`, `call screen`, `with`, Ren'Py control flow (`jump`, `call`, `return` at label level)
- Skip: `python early:` blocks (out of scope, noted in scope boundaries)
- Preserve comment lines within `init python:` blocks (they may be meaningful to the Python code)

**Test scenarios:**
- Happy path: parse a file with a single `init python:` block, verify extracted code is syntactically valid Python
- Happy path: parse `init 100 python:` block, verify priority=100 is captured
- Happy path: parse `init python in mystore:` block, verify store_name="mystore"
- Happy path: parse `define v = Character("Vince")` → Define with name="v"
- Happy path: parse `default persistent.save_data = None` → Default with name="persistent.save_data"
- Happy path: parse `label fenton_initialize:` → Label with name="fenton_initialize"
- Happy path: parse file with multiple `init python:` blocks (like terminalgame's display.rpy has two)
- Edge case: `init python:` followed by blank line then indented code (like globals.rpy line 4-5)
- Edge case: mixed content — `init python:` block, then label, then another `init python:` block (like fenton.rpy)
- Edge case: indentation uses tabs instead of spaces
- Edge case: nested indentation within init python block (function defs, if statements, for loops)
- Edge case: file with no extractable Python (pure Ren'Py dialogue)
- Edge case: `label name(param1, param2):` with parameters
- Error path: malformed file (e.g., indentation error) — parser should report file and line number

**Verification:**
- Parser correctly extracts all `init python:` blocks from every terminalgame `.rpy` file
- Extracted code strings are valid Python (`compile()` succeeds)
- All labels from terminalgame are captured in metadata

---

- [ ] **Unit 3: Mock Ren'Py Namespace**

**Goal:** Provide a fake `renpy` module with exception-based control flow, store namespace, and stubs for common APIs so that game Python executes without crashing.

**Requirements:** R4, R5

**Dependencies:** Unit 1 (exception types exported from `__init__.py`)

**Files:**
- Create: `src/pytest_renpy/mock_renpy/__init__.py`
- Create: `src/pytest_renpy/mock_renpy/store.py`
- Create: `src/pytest_renpy/mock_renpy/exports.py`
- Create: `src/pytest_renpy/mock_renpy/config.py`
- Create: `src/pytest_renpy/mock_renpy/persistent.py`
- Create: `src/pytest_renpy/mock_renpy/display.py`
- Create: `src/pytest_renpy/mock_renpy/random.py`
- Test: `tests/test_mock_renpy.py`

**Approach:**

**Store namespace** (`store.py`):
- `StoreNamespace` must be a `dict` subclass (or the exec call must use a plain dict). This is required because `exec(code, namespace)` needs a dict as its globals argument, and `globals()` inside exec'd code returns that same dict. A custom class with only `__getattr__`/`__setattr__` won't work — the object passed to `exec()` must behave as a real dict
- Provides both attribute access (`store.x`) and dict access (`store['x']`) via `__getattr__`/`__setattr__` wired to dict operations. Must handle collision with dict built-in method names (`items`, `keys`, `values`, `get`, `pop`, `update`, etc.) — `__getattr__` should only fire for names not in `dir(dict)`, or use `__getattribute__` that falls through to `dict.__getattribute__` first and only looks up dict keys on `AttributeError`
- No snapshot/restore — each test gets a fresh namespace via re-exec (deep-copy is ruled out; see Key Technical Decisions)

**Control flow** (`exports.py`):
- `jump(target)` → records target on mock, raises `JumpException(target)`
- `call(target)` → records target, raises `CallException(target)`
- `return_statement()` → raises `ReturnException`
- `quit()` → records quit, raises `QuitException`
- `pause(duration)` → no-op, records duration
- `notify(msg)` → records message
- `display_menu(options)` → records options, returns first option's value (deterministic default for testing)
- `scene()` → no-op, records call
- `show(name, at_list=None)` → no-op, records name and position
- `hide(name)` → no-op, records name
- `with_statement(transition)` → no-op, records transition
- `version()` → returns a static version string

**Config** (`config.py`):
- Attribute bag with sensible defaults: `config.gamedir`, `config.savedir`, `config.rollback_enabled`, etc.
- Any attribute access returns a default rather than raising `AttributeError`

**Persistent** (`persistent.py`):
- Object with attribute access, backed by a dict
- Starts empty, supports arbitrary attribute assignment
- Reset between tests

**Display stubs and Ren'Py globals** (`display.py`):
- `Transform(**kwargs)` → records kwargs, returns a stub object
- `TintMatrix(color)` → records color, returns a stub object
- `Character(name, **kwargs)` → returns a callable stub (Characters are called to display dialogue)
- `Dissolve(duration)`, `dissolve`, `fade` → transition stubs
- `right`, `left` → position constants

**Random** (`random.py`):
- Wraps stdlib `random.Random` with seed=0 default
- Exposes same interface as `renpy.random` (`.randint()`, `.choice()`, `.random()`, etc.)

**Mock renpy module** (`__init__.py`):
- Assembles all sub-modules into a single mock object that can be injected as `renpy` into exec'd namespaces
- Permissive fallback via `__getattr__`: accessing any unimplemented `renpy.*` attribute returns a no-op callable stub (records the call but does not raise `AttributeError`). This ensures projects using uncommon APIs degrade gracefully rather than crashing
- `create_mock()` factory returns a fresh mock instance
- Tracks call history: `mock.jumps`, `mock.calls`, `mock.pauses`, `mock.notifications`, `mock.quit_called`, `mock.menus`, `mock.scenes`, `mock.shown`, `mock.hidden`

**Test scenarios:**
- Happy path: `renpy.jump("target")` raises `JumpException` with target="target" and records the jump
- Happy path: `renpy.call("target")` raises `CallException` and records the call
- Happy path: `renpy.quit()` raises `QuitException` and sets `quit_called = True`
- Happy path: `renpy.pause(0.2)` does not raise, records duration
- Happy path: `renpy.display_menu([("Option A", "a"), ("Option B", "b")])` returns "a" (first option) and records the menu
- Happy path: `renpy.scene()` records the scene clear
- Happy path: `renpy.show("character", at_list=[right])` records show with position
- Happy path: `renpy.hide("character")` records the hide
- Happy path: `renpy.version()` returns a string
- Happy path: `renpy.random.randint(0, 9)` returns deterministic value with default seed
- Happy path: `renpy.random.randint` returns same sequence after re-seeding with same seed
- Happy path: `StoreNamespace` supports both `store.x` and `store['x']` access
- Happy path: `StoreNamespace` is a valid dict for `exec(code, store)` — `globals()` inside exec'd code returns the store
- Happy path: `persistent.save_data = {...}` works with attribute assignment
- Happy path: `Transform(matrixcolor=..., zoom=1.7)` returns stub, kwargs accessible
- Happy path: `TintMatrix("#ff0000")` returns stub, color accessible
- Happy path: `Character("Vince", color="#8B2A3A")` returns callable stub
- Happy path: `config.gamedir` returns a sensible default string
- Edge case: accessing undefined `config.anything` returns a default (not `AttributeError`)
- Edge case: `renpy.random` with explicit seed produces reproducible sequence
- Integration: exec a snippet that calls `renpy.jump("x")` in a namespace with mock renpy injected — `JumpException` propagates correctly
- Integration: exec a snippet using `globals()[name](args)` dynamic dispatch — function defined in the namespace is found and called correctly

**Verification:**
- All mock APIs from the three reference projects work without crashing: `renpy.jump`, `renpy.call`, `renpy.quit`, `renpy.pause`, `renpy.display_menu`, `renpy.scene`, `renpy.show`, `renpy.hide`, `renpy.version`, `renpy.random.randint`, `persistent.*`, `Transform`, `TintMatrix`, `Character`, `config.*`

---

- [ ] **Unit 4: Project Loader**

**Goal:** Given a project directory, parse all `.rpy` files, sort init blocks by priority, and produce a loadable project representation.

**Requirements:** R7, R10

**Dependencies:** Unit 2 (parser), Unit 3 (mock renpy)

**Files:**
- Create: `src/pytest_renpy/loader.py`
- Test: `tests/test_loader.py`

**Approach:**
- `load_project(project_dir) -> ProjectData` globs `**/*.rpy` under the project directory (typically `game/`)
- Parses each file via `rpy_parser.parse_file()`
- Collects all `InitBlock`s across files, sorts by priority (lower runs first, ties broken by file path then line number for determinism)
- Collects all `Define`s and `Default`s
- Collects all `Label`s as metadata
- `ProjectData` holds the sorted init blocks, defines, defaults, labels, and a method to execute into a fresh namespace
- `execute_into(namespace, mock_renpy)` runs all init blocks in priority order via 2-argument `exec(block.code, namespace)`, with `renpy`, `persistent`, `Character`, `Transform`, `TintMatrix`, and other Ren'Py globals pre-injected into the namespace dict. All blocks share the same namespace dict so definitions accumulate. Then applies `define` and `default` values via `eval(expression, namespace)` in the same namespace, so expressions can reference mock objects and previously-defined store variables. `define` values are set before `default` values (matching Ren'Py semantics)
- Ensures the project's `game/` directory is on `sys.path` during exec, so `import` statements in init blocks (e.g., `from utils import *`) can find `.py` files in the game directory. The `sys.path` insertion is scoped via context manager or try/finally within `execute_into()` and removed after exec completes, preventing pollution of the host process's import namespace
- `execute_into()` wraps each `exec(block.code, namespace)` in a try/except that catches exceptions and re-raises with `source_file` and `source_line` context from the `InitBlock` metadata, so test failures during fixture setup include the originating `.rpy` file and line number rather than opaque exec tracebacks
- Cache `ProjectData` at the call site (session-scoped fixture) — parsing is the expensive part; re-exec per test is cheap

**Test scenarios:**
- Happy path: load a directory with one .rpy file, verify init blocks are extracted and executable
- Happy path: load terminalgame's `game/` directory, verify all init blocks from all files are collected
- Happy path: `init 100 python:` block sorts after `init python:` (priority 0) block
- Happy path: define and default values are applied to the namespace after init blocks execute
- Edge case: two files with same-priority init blocks — deterministic ordering by file path
- Edge case: empty directory (no .rpy files) — returns empty ProjectData, no error
- Edge case: .rpy file with no init python blocks — file is parsed but contributes no init blocks
- Integration: execute terminalgame's full project into a namespace with mock renpy — `game_print`, `check_for_commands`, `create_cmd` etc. are all callable in the resulting namespace

**Verification:**
- All terminalgame functions are accessible in the loaded namespace
- `namespace['game_print']` is callable
- `namespace['cmd_dict']` contains the expected command structure
- Loading terminalgame completes in under 500ms

---

- [ ] **Unit 5: Pytest Fixtures**

**Goal:** Provide `renpy_game`, `renpy_store`, and `renpy_mock` fixtures that give each test a fresh, isolated game environment.

**Requirements:** R6, R9

**Dependencies:** Unit 3 (mock renpy), Unit 4 (loader)

**Files:**
- Create: `src/pytest_renpy/fixtures.py`
- Test: `tests/test_fixtures.py`

**Approach:**

`renpy_project` (session scope):
- Reads `--renpy-project` option, resolves the game directory (looks for `game/` subdirectory)
- Calls `loader.load_project()` once per session
- Caches the `ProjectData`

`renpy_mock` (function scope):
- Creates a fresh mock renpy instance via `create_mock()`
- Yields it for test use — test can inspect `mock.jumps`, `mock.quit_called`, etc.

`renpy_store` (function scope):
- Creates a fresh `StoreNamespace`
- Executes the project's init blocks into it (via `ProjectData.execute_into()`)
- Yields the populated namespace

`renpy_game` (function scope):
- Combines `renpy_mock` + `renpy_store` into a single convenience object
- `renpy_game.store` — the populated namespace
- `renpy_game.mock` — the mock renpy (for inspecting recorded jumps, calls, etc.)
- `renpy_game.labels` — label metadata from the project
- Calling functions: `renpy_game.store.game_send()` calls the function directly in the store namespace

**Test scenarios:**
- Happy path: `renpy_game` fixture provides a store with all game globals loaded
- Happy path: `renpy_mock` fixture resets between tests (no state leakage)
- Happy path: `renpy_store` fixture provides fresh state — modifying `store.typing_message` in one test doesn't affect the next
- Happy path: `renpy_game.labels` contains label names from the project
- Edge case: test without `--renpy-project` flag — uses current directory as default
- Edge case: `--renpy-project` points to directory without `game/` subdirectory — clear error message
- Integration: two sequential tests that both modify `store.cmd_dict` — second test sees original state

**Verification:**
- Fixtures are auto-available (no imports needed in user test files)
- Each test gets isolated state
- Fixture setup is fast enough that 50 tests complete in under 2 seconds

---

- [ ] **Unit 6: Proof-of-Concept Tests Against terminalgame**

**Goal:** Write real tests against the terminalgame project that validate the full plugin stack and catch the known `delete_cmd` bug.

**Requirements:** R1-R10 (end-to-end validation)

**Dependencies:** Unit 5 (fixtures complete)

**Files:**
- Create: `examples/terminalgame/conftest.py`
- Create: `examples/terminalgame/test_commands.py`
- Create: `examples/terminalgame/test_display.py`
- Create: `examples/terminalgame/test_markup.py`
- Create: `examples/terminalgame/test_game_flow.py`

**Approach:**
- `conftest.py` configures `--renpy-project` to point at the terminalgame game directory
- Tests call functions from the store namespace directly (e.g., `renpy_game.store.game_send()`)
- Tests set up store state, call functions, and assert on store mutations or raised exceptions
- The known `delete_cmd("temporary", 'start')` bug should cause a test failure that demonstrates the plugin's value

**Test scenarios:**

Command routing (`test_commands.py`):
- Happy path: `check_for_commands("quit")` with quit usable → calls `quit_command` → raises `QuitException`
- Happy path: `create_cmd` adds a command to `cmd_dict['temporary_cmds']` and it becomes routable
- Happy path: `delete_cmd("temporary_cmds", "start")` removes the command (correct category name)
- Error path: `delete_cmd("base_cmds", "quit")` — the known bug — `delete_cmd` ignores its `category` parameter entirely and always operates on `cmd_dict['temporary_cmds']`, so passing `"base_cmds"` still deletes from `temporary_cmds`. Test proves the function never uses its category argument
- Happy path: `check_for_commands("help quit")` with help usable → calls `help_command` → adds to `terminal_log`
- Happy path: `take_input("destination")` disables non-exempt commands, sets `input_mode['active']`

Display logic (`test_display.py`):
- Happy path: `game_print("hello")` appends "hello" to `terminal_log`
- Happy path: `game_print` with string longer than `LOG_WIDTH_LIMIT` wraps into multiple lines
- Edge case: `game_print` when `terminal_log` is at `LOG_HEIGHT_LIMIT` pops oldest line
- Happy path: `game_print` with `replace_previous_line=True` replaces last log entry

Markup parsing (`test_markup.py`):
- Happy path: `does_show_character("a")` returns `True`
- Happy path: `does_show_character("[")` returns `False` and sets `in_markup = True`
- Happy path: `handle_end_markup()` processes `color=#ffffff` → sets `markup_data["color"]`
- Happy path: `handle_end_markup()` processes `/color` → resets `markup_data["color"]` to `None`

Font resolution (`test_display.py`):
- Happy path: `get_font("a")` returns `terminal_formatting_data["font"]` ("terminal")
- Edge case: `get_font("brick")` returns "fallback"
- Happy path: `get_character_asset("a")` returns `"characters/terminal/a_char.png"`
- Happy path: `get_character_asset("!")` uses SPECIAL mapping → `"characters/terminal/exclamation_mark_char.png"`

Game flow (`test_game_flow.py`):
- Happy path: `game_send()` with `typing_message = "quit"` and quit usable → prints `">>> quit"` to log, raises (eventually) `QuitException`
- Happy path: after `game_send()`, `typing_message` is reset to `""`
- Integration: set up store for Fenton intro gateway: `fenton_intro_start_gateway("start")` → calls `delete_cmd` then `renpy.jump('fenton_intro_start')` → raises `JumpException` with target `'fenton_intro_start'`

**Verification:**
- All tests pass except the one demonstrating the `delete_cmd` bug (which should be an expected failure or clearly documented)
- Tests run in under 1 second total
- Tests demonstrate the plugin's value proposition: testing game logic without the engine

---

- [ ] **Unit 7: Packaging and Documentation**

**Goal:** Ensure the package is pip-installable with proper metadata, and provide a README with usage instructions.

**Requirements:** R8

**Dependencies:** Unit 6 (proof-of-concept validates everything works)

**Files:**
- Modify: `pyproject.toml` (finalize metadata: description, classifiers, URLs, license)
- Modify: `README.md` (replace placeholder with usage guide)

**Approach:**
- Add proper classifiers: `Framework :: Pytest`, `Programming Language :: Python :: 3`, `Topic :: Software Development :: Testing`
- Add project URLs: homepage, repository
- Verify `pip install -e .` works from clean state
- README covers: installation, basic usage (point at a Ren'Py project, write a test, run pytest), fixture API reference, exception types for control flow testing

**Test expectation: none** — this unit is packaging and documentation, no behavioral changes.

**Verification:**
- `pip install -e .` from a clean virtualenv succeeds
- `pytest --help` shows `--renpy-project` option
- A new user can follow the README to write their first test

## System-Wide Impact

- **Interaction graph:** The plugin hooks into pytest's collection and fixture lifecycle. No callbacks or middleware beyond standard pytest hooks.
- **Error propagation:** Parser errors should include file path and line number. Loader errors should identify which `.rpy` file failed. Fixture errors should distinguish between "project not found" and "parse/exec failure."
- **State lifecycle risks:** The main risk is store mutation leaking between tests. Mitigated by function-scoped fixtures that re-exec init blocks into a fresh namespace per test.
- **API surface parity:** The fixture API (`renpy_game`, `renpy_store`, `renpy_mock`) is the public contract. Exception types (`JumpException`, etc.) are importable from `pytest_renpy`.
- **Integration coverage:** Unit 6 provides end-to-end coverage against a real Ren'Py project.
- **Unchanged invariants:** The plugin does not modify any `.rpy` files, does not require the Ren'Py SDK, and does not affect normal pytest behavior for non-Ren'Py tests.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `exec()` of parsed Python fails due to missing globals or import context | The namespace is pre-populated with mock renpy, display stubs, Ren'Py globals (`Character`, `Transform`, etc.), and builtins. Standard library imports work by default because Python's `exec()` injects `__builtins__` into the globals dict. The project's `game/` directory is added to `sys.path` so `.py` file imports (e.g., `from utils import *`) resolve correctly. Failures are surfaced with source file + line info |
| `globals()` calls within exec'd code return the wrong namespace | Enforced by using 2-argument `exec(code, namespace)` exclusively. The 3-argument form is never used. Test against terminalgame's `globals()[destination](message)` dispatch and `globals()[var_name]` introspection patterns |
| `global` keyword in exec'd functions resolves against wrong namespace | 2-argument `exec(code, namespace)` ensures `global x` declarations resolve against the namespace dict. Verified by test: define a function with `global x` in exec'd code, call it, confirm `x` appears in the namespace |
| Deep-copy of namespace breaks function isolation | Not applicable — deep-copy is ruled out (see Key Technical Decisions). Each test re-executes all init blocks into a fresh namespace dict, ensuring function `__globals__` references point to the test's own namespace |
| Cross-file dependencies break when execution order is wrong | Init priority sorting handles this. All cross-file function references in the three reference projects are inside function bodies (deferred calls), not at module level, so any ordering of same-priority blocks works. File-path ordering provides additional determinism |
| Performance: re-exec per test is too slow for large projects | Parse result is cached at session scope. Only exec (which is fast for typical init blocks) happens per test. Benchmark against terminalgame's ~13 files |
| Parser mishandles edge cases in .rpy syntax | Extensive test scenarios in Unit 2. Real-world validation in Unit 6 against terminalgame |
| Mock surface incomplete for some Ren'Py projects | Mock covers APIs observed across three reference projects of varying complexity. The mock uses permissive defaults (unknown `config.*` returns a default, unknown `renpy.*` does not crash) so projects using uncommon APIs degrade gracefully |

## Sources & References

- **Origin document:** [docs/plans/layer1-mock-unit-testing.md](docs/plans/layer1-mock-unit-testing.md)
- **Follow-up plan:** [docs/plans/layer2-label-flow-integration.md](docs/plans/layer2-label-flow-integration.md)
- **Target game (extreme test case):** terminalgame project at `/projects/xander/terminalgame/` — aggressive Python usage with `globals()` dispatch, 41 functions across 8 files
- **Reference game (visual novel):** the-kid-and-the-king-of-chicago at `/projects/masked_fox/the-kid-and-the-king-of-chicago/` — typical complexity, `.py` file imports, `Character` defines
- **Reference game (RPG):** minimum-viable-rpg-renpy at `/projects/masked_fox/minimum-viable-rpg-renpy/` — moderate complexity, scene management APIs, `Transform` in defines, functions in label `python:` blocks
- Related code: terminalgame's `game/keyboard.rpy` (command routing, `globals()` dispatch), `game/display.rpy` (game_print, markup), `game/globals.rpy` (store setup)
- External docs: pytest plugin development guide, Ren'Py Python statement reference

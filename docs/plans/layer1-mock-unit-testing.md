# Plan: pytest-renpy Layer 1 — Mock-Based Unit Testing

## Goal

A reusable pytest plugin (`pytest-renpy`) that enables unit testing Python logic embedded in `.rpy` files without running the Ren'Py engine. Installable via pip, usable across any Ren'Py project.

## Package Structure

```
pytest-renpy/
  pyproject.toml
  README.md
  src/
    pytest_renpy/
      __init__.py
      plugin.py              # pytest plugin entry point
      rpy_parser.py          # .rpy file parser → importable Python
      mock_renpy/
        __init__.py          # top-level renpy namespace mock
        store.py             # renpy.store mock (game globals)
        exports.py           # renpy.jump, renpy.call, renpy.pause, etc.
        config.py            # renpy.config mock
        persistent.py        # persistent storage mock
        display.py           # Transform, TintMatrix stubs
        random.py            # renpy.random mock
      fixtures.py            # pytest fixtures (renpy_game, renpy_store, etc.)
      loader.py              # loads extracted Python into a test namespace
  tests/
    test_rpy_parser.py
    test_mock_renpy.py
    test_fixtures.py
    test_integration.py      # tests against a sample .rpy project
  examples/
    terminalgame/            # this game as first proof-of-concept
      test_markup.py
      test_commands.py
      test_fonts.py
      conftest.py
```

## Components

### 1. `.rpy` File Parser (`rpy_parser.py`)

**Purpose:** Extract Python code from `.rpy` files so it can be imported and tested.

**What it needs to handle:**

| Ren'Py Construct | Parser Behavior |
|------------------|-----------------|
| `init python:` block | Extract indented Python body |
| `init python in <store>:` | Extract into namespaced module |
| `python:` block (inside labels) | Extract as callable function |
| `define x = ...` | Convert to assignment |
| `default x = ...` | Convert to assignment with default semantics |
| `$ statement` | Extract as Python statement |
| Labels (`label foo:`) | Track as entry points, expose as metadata |
| Ren'Py statements (`say`, `show`, `scene`, `menu`) | Skip/stub |
| `screen` definitions | Skip (Layer 2 territory) |
| Comments (`#`) | Preserve |
| String interpolation (`[variable]` in dialogue) | Skip (not Python) |

**Approach:**
- Line-by-line state machine parser (not a full AST)
- Ren'Py's `.rpy` syntax is indentation-based and relatively regular
- Output: a Python module string that can be `exec()`'d into a namespace
- Cache parsed results (`.rpy` → `.py` mapping) for performance

**Key design decisions:**
- Should the parser produce importable `.py` files on disk, or parse-and-exec at test time?
  - Recommendation: parse-and-exec at test time (no generated files to manage)
- How to handle `init` ordering? Ren'Py processes `init` blocks by priority.
  - Recommendation: sort extracted blocks by `init offset` value, default 0

**Edge cases to handle:**
- `init N python:` (priority numbers)
- Multi-file projects (globals defined in one file, used in another)
- Conditional init: `if renpy.mobile:` guards inside init blocks
- Ren'Py string syntax: `_("translatable")` wrapping

### 2. Mock Ren'Py Namespace (`mock_renpy/`)

**Purpose:** Provide a fake `renpy` module that game Python code can call without crashing.

**APIs to mock (based on this game + common Ren'Py patterns):**

| API | Mock Behavior |
|-----|---------------|
| `renpy.jump(label)` | Record the jump target, raise `JumpException` |
| `renpy.call(label)` | Record the call target, raise `CallException` |
| `renpy.call_in_new_context(label)` | Record, raise `CallException` |
| `renpy.return_statement()` | Raise `ReturnException` |
| `renpy.pause(duration)` | No-op, record the pause |
| `renpy.quit()` | Record quit, raise `QuitException` |
| `renpy.random.randint(a, b)` | Delegate to stdlib `random` (seedable) |
| `renpy.notify(msg)` | Record notification |
| `renpy.input(prompt)` | Return from a configurable queue |
| `persistent` | Dict-like object with attribute access |
| `Transform(**kwargs)` | Record kwargs, return stub object |
| `TintMatrix(color)` | Record color, return stub object |
| `config.*` | Attribute bag with sensible defaults |
| `store` (implicit) | The test namespace itself |

**Control flow design:**

Ren'Py uses exceptions for control flow (`renpy.jump` raises internally to unwind the stack). The mock should replicate this:

```python
class JumpException(Exception):
    def __init__(self, target):
        self.target = target

def jump(target):
    store._jumps.append(target)
    raise JumpException(target)
```

Tests can then either:
- Catch these exceptions to verify flow: `with pytest.raises(JumpException, match="handle_tick")`
- Use a helper that calls the function and returns the jump target: `assert calls(game_send) == "handle_tick"`

**Store mock:**

The "store" is Ren'Py's implicit global namespace where all game variables live. The mock provides:
- Attribute-style access (`store.typing_message`)
- Dict-style access (`store['typing_message']`)
- Reset between tests (fixture scoped)
- Pre-population from parsed `default`/`define` statements

### 3. Pytest Plugin (`plugin.py`)

**Registers:**
- `pytest_configure` hook to add markers (`@pytest.mark.renpy`)
- `conftest.py` auto-injection for Ren'Py projects
- CLI options: `--renpy-project <path>` to specify game directory

### 4. Fixtures (`fixtures.py`)

| Fixture | Scope | Provides |
|---------|-------|----------|
| `renpy_project` | session | Parsed project (all `.rpy` files loaded) |
| `renpy_store` | function | Fresh store namespace with game defaults |
| `renpy_mock` | function | The mock renpy module (access jumps, calls, etc.) |
| `renpy_game` | function | Combined: store + mock + all game functions loaded |

**Usage example:**

```python
def test_help_command_prints_info(renpy_game):
    # Setup
    renpy_game.store.cmd_dict['base_cmds']['help']['usable'] = True
    
    # Act
    renpy_game.call('help_command', 'help quit')
    
    # Assert
    assert any('saves changes and closes' in line for line in renpy_game.store.terminal_log)


def test_game_send_routes_to_quit(renpy_game):
    renpy_game.store.cmd_dict['base_cmds']['quit']['usable'] = True
    renpy_game.store.typing_message = "quit"
    
    with pytest.raises(JumpException) as exc:
        renpy_game.call('game_send')
    
    # quit_command calls renpy.quit()
    assert renpy_game.mock.quit_called
```

### 5. Project Loader (`loader.py`)

**Responsibility:** Given a project directory, parse all `.rpy` files, sort by init priority, execute them in order into a store namespace, and return the populated namespace.

**Load order:**
1. Parse all `.rpy` files in `game/`
2. Sort `init` blocks by priority (lower runs first)
3. Execute into a shared namespace with mock renpy available
4. Return the namespace as the "store"

**Multi-file dependencies:** Many Ren'Py projects define globals in one file and use them in another. The loader must process all files before any test runs, respecting init order.

## Implementation Phases

### Phase 1: Parser + Smoke Test (2-3 days)
- Implement `rpy_parser.py` — handle `init python:`, `define`, `default`, `$`
- Test against this game's `.rpy` files
- Verify extracted Python is syntactically valid

### Phase 2: Mock Renpy (2-3 days)
- Implement core mocks: jump, call, pause, quit, random, persistent
- Implement Transform/TintMatrix stubs
- Implement store namespace with attribute access

### Phase 3: Fixtures + Plugin (1-2 days)
- Wire up pytest plugin entry point
- Implement fixtures (renpy_project, renpy_store, renpy_mock, renpy_game)
- Implement project loader with init-priority ordering

### Phase 4: Proof of Concept (2-3 days)
- Write tests for this game:
  - Markup parsing (does_show_character, handle_end_markup)
  - Command routing (check_for_commands, create_cmd, delete_cmd)
  - Font resolution (get_font, get_character_asset)
  - Game print (line wrapping, log height limit)
  - Input mode (take_input flow)
- Verify tests catch the `delete_cmd("temporary", 'start')` bug

### Phase 5: Packaging + Docs (1-2 days)
- pyproject.toml with pytest11 entry point
- README with usage guide
- Publish-ready (or at minimum installable via `pip install -e .`)

## Open Questions

1. **How to handle `renpy.jump()` in tests?** Two options:
   - Exception-based (mimics real Ren'Py) — more realistic but tests must catch exceptions
   - Record-and-continue (mock swallows the jump) — simpler tests but may miss bugs where code after a jump shouldn't execute
   - **Recommendation:** Exception-based by default, with a `@pytest.mark.renpy(swallow_jumps=True)` option

2. **Should the parser handle Ren'Py's `_ren.py` files?**
   - These are Python files with embedded Ren'Py in docstrings
   - Lower priority — they're already importable Python
   - Include in Phase 5 if time permits

3. **How to handle `renpy.random`?**
   - Seed it deterministically by default (reproducible tests)
   - Allow tests to configure specific sequences

4. **Namespace isolation between tests:**
   - Each test gets a fresh store (function-scoped fixture)
   - But what about `init python:` side effects? The parser output is cached, but execution happens fresh per test.

## Success Criteria

- [ ] Can test all Python logic in this game's `.rpy` files without extracting anything manually
- [ ] Tests run with standard `pytest` command
- [ ] No dependency on Ren'Py SDK at test time
- [ ] Catches the known `delete_cmd("temporary", 'start')` bug
- [ ] Installable as a pip package in other Ren'Py projects
- [ ] < 1 second test suite startup for a project this size

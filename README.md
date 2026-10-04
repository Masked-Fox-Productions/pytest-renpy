# pytest-renpy

Test Ren'Py game logic with standard pytest — no engine required.

## Install

```sh
pip install pytest-renpy
```

## Usage

Point `--renpy-project` at your Ren'Py project directory (defaults to `.`):

```sh
pytest --renpy-project=/path/to/my-game
```

The plugin parses `.rpy` files, extracts init-time Python (`init python:` blocks, `define`, `default`), and executes it under a mock `renpy` namespace in Ren'Py's init order.

### Write a test

```python
import pytest
from pytest_renpy import JumpException, QuitException

def test_game_state(renpy_game):
    assert renpy_game.store["score"] == 0

def test_command_routing(renpy_game):
    with pytest.raises(QuitException):
        renpy_game.store["check_for_commands"]("quit")
    assert renpy_game.mock.quit_called

def test_jump_target(renpy_game):
    with pytest.raises(JumpException) as exc_info:
        renpy_game.store["some_function"]()
    assert exc_info.value.target == "next_label"
```

### Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `renpy_game` | function | Combined object with `.store`, `.mock`, `.labels`, `.load_errors`, and `.run_label_python(name)` |
| `renpy_store` | function | Fresh `StoreNamespace` with all init blocks executed |
| `renpy_mock` | function | Fresh mock `renpy` module with call tracking |
| `renpy_load_errors` | function | `(item, exception)` pairs skipped while loading (skip mode only) |
| `renpy_project` | session | Parsed project data (cached, parsed once) |

Each function-scoped fixture re-executes all init blocks into a fresh namespace, so tests are fully isolated.

### Load errors

By default a load error (an init block, `define`, or `default` that raises, or a `.rpy` statement that is never terminated) fails the test. Real projects often have a few blocks that can't run under the mock; load them anyway and assert on what failed:

```ini
[pytest]
renpy_on_error = skip
```

(or `pytest --renpy-on-error=skip`)

```python
def test_only_known_load_errors(renpy_game):
    for item, exc in renpy_game.load_errors:
        assert item.source_file.endswith("screens.rpy"), f"{item.source_file}:{item.source_line}: {exc}"
```

Every error names `source_file:source_line`, and tracebacks from game code point at the `.rpy` line.

### Building state from labels

Labels are metadata by default; their bodies never run at load. To build real game state that a label sets up with `$` lines or `python:` blocks, opt in:

```python
def test_board_state(renpy_game):
    result = renpy_game.run_label_python("init_board_dicts")
    assert renpy_game.store["Entities"]
    print(result.skipped)  # dialogue, show/scene, menus, if blocks... not run
```

Only the label's top-level Python statements run, in order. `renpy.jump()` and friends still raise `JumpException` etc. On a raw namespace, use `project.run_label_python(name, namespace)`.

### Mock renpy

The mock tracks calls for assertions:

```python
def test_display_menu(renpy_game):
    result = renpy_game.mock.display_menu([("Option A", "a"), ("Option B", "b")])
    assert result == "a"  # returns first option by default
    assert len(renpy_game.mock.menus) == 1
```

Available tracking: `mock.jumps`, `mock.calls`, `mock.pauses`, `mock.notifications`, `mock.quit_called`, `mock.menus`, `mock.scenes`, `mock.shown`, `mock.hidden`, `mock.transitions`.

`renpy.random` is seeded with `0` by default for deterministic tests.

### Exception types

Control flow uses exceptions, matching real Ren'Py behavior:

- `JumpException` — raised by `renpy.jump(target)`, has `.target`
- `CallException` — raised by `renpy.call(target)`, has `.target`
- `ReturnException` — raised by `renpy.return_statement()`
- `QuitException` — raised by `renpy.quit()`

Import from `pytest_renpy`:

```python
from pytest_renpy import JumpException, CallException, ReturnException, QuitException
```

## What gets parsed

Files are split into Ren'Py *logical lines* first, so statements spanning lines (multi-line dict literals, triple-quoted strings, multi-line dialogue, backslash continuations) parse as one statement.

- `init python:` blocks (with priority and named stores), including ones nested inside labels
- `define` and `default` statements, including multi-line ones and ones inside labels
- `python:` blocks and `$` lines directly inside `init:` blocks
- `transform` names (bound to a placeholder; ATL is not emulated)
- `label` declarations (available as metadata, plus their bodies for `run_label_python`)

Screens are skipped entirely; plain `python:`/`$` in a label body stays runtime-only.

### Init order and defaults

Init blocks, defines, and defaults run as one stream ordered by (priority, file, line), as in Ren'Py: priority comes from `init N`, `define N`/`default N`, `init offset` (block-scoped), or an enclosing `init N:` block; files sort by their path relative to the game directory.

- `define a.b = x` sets an attribute on the named store, creating it if needed (`config.*`, `gui.*`, `build.*` included); `define persistent.x` sets it only if it is `None`.
- `default persistent.x`, `default gui.x`, and `default preferences.x` apply at their place in the stream. Other defaults are evaluated after all init code, in stream order, and overwrite init-time values — except names you pre-seed in the namespace passed to `execute_into` (or a `persistent=` you pass in).
- `default config.x`, `define preferences.x`, and `define`/`default renpy.x` are load errors, as in Ren'Py.

Known divergences: all named stores share one namespace; `init: call some_label` does not run that label (use `run_label_python`); `python early` is skipped; game code compiles with the host Python, not Ren'Py's bundled 3.9.

## What's mocked

`renpy.jump`, `renpy.call`, `renpy.quit`, `renpy.pause`, `renpy.display_menu`, `renpy.scene`, `renpy.show`, `renpy.hide`, `renpy.with_statement`, `renpy.version`, `renpy.notify`, `renpy.random`, `renpy.config` (also `config`), `persistent`, `gui`, `build`, `preferences`, `style` (permissive bags: writes stick, unknown reads and calls are recorded no-ops), `_`/`__`/`_p`, `Character`, `Transform`, `TintMatrix`, `Dissolve`, position constants (`right`, `left`, `center`, `truecenter`), transition constants (`dissolve`, `fade`), and recording stand-ins for `Borders`, `Pause`, `MoveTransition`, `BarValue`, `Quit`.

Unknown names still raise `NameError`, so genuine mistakes in game code surface.

Unimplemented `renpy.*` attributes return no-op stubs instead of raising errors.

## Integration Testing (Layer 2)

Layer 2 boots a real headless Ren'Py process and communicates over IPC, enabling tests that exercise label flow, store mutations, menu interaction, and label-scoped functions — things Layer 1's mock can't reach.

### Prerequisites

Download the [Ren'Py SDK](https://www.renpy.org/latest.html) (8.x).

### Configuration

```sh
pytest --renpy-project=/path/to/my-game --renpy-sdk=/path/to/renpy-sdk
```

Tests that use Layer 2 fixtures will be skipped if `--renpy-sdk` is not set. Layer 1 tests are unaffected.

### Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `renpy_session` | function | Fresh headless Ren'Py engine per test (primary fixture) |
| `renpy_engine` | function | Alias for `renpy_session` |

### API

```python
def test_label_flow(renpy_session):
    # Jump to a label — engine executes it, yields at the next say/pause/menu
    result = renpy_session.jump("start")

    # Read store variables
    store = renpy_session.get_store("score", "player_name")
    assert store["score"] == 0

    # Set store variables (for game-specific input adapters)
    renpy_session.set_store(player_name="Alice")

    # Advance past a say/pause
    renpy_session.advance(1)

    # Advance until a condition is met
    result = renpy_session.advance_until(
        condition=lambda s: s.get("score", 0) > 10,
        max_ticks=100,
    )
    assert result.status == "reached"

def test_menu_interaction(renpy_session):
    result = renpy_session.jump("choose_option")

    # If the label hits a menu, result.raw["status"] == "menu_waiting"
    options = renpy_session.get_menu_options()
    # [{"text": "Apple"}, {"text": "Banana"}]

    menu_result = renpy_session.select_menu(1)        # by index
    menu_result = renpy_session.select_menu("Apple")  # or by text
```

### How it works

The engine runner:
1. Copies your game directory to a temp location
2. Injects a `_test_harness.rpy` that patches `renpy.ui.interact` and `renpy.display_menu`
3. Launches the SDK's Python with SDL dummy drivers (no display)
4. Communicates over a Unix domain socket using JSON lines

Each test gets a fresh engine process for perfect isolation. The original project directory is never modified.

### Troubleshooting

- **"SDK Python not found"**: Check that `--renpy-sdk` points to the SDK root (containing `renpy.py` and `lib/`)
- **Engine boot timeout**: Some games have parse errors that prevent headless boot. Check the error output for details
- **"Invalid window" errors**: The harness patches transitions to no-ops, but some games may trigger display init in unexpected places

## Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
```

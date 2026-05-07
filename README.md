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

The plugin parses `.rpy` files, extracts `init python:` blocks, and executes them under a mock `renpy` namespace.

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
| `renpy_game` | function | Combined object with `.store`, `.mock`, and `.labels` |
| `renpy_store` | function | Fresh `StoreNamespace` with all init blocks executed |
| `renpy_mock` | function | Fresh mock `renpy` module with call tracking |
| `renpy_project` | session | Parsed project data (cached, parsed once) |

Each function-scoped fixture re-executes all init blocks into a fresh namespace, so tests are fully isolated.

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

- `init python:` blocks (with priority and named stores)
- `define` statements (evaluated in namespace)
- `default` statements (set if not already defined)
- `label` declarations (available as metadata)

## What's mocked

`renpy.jump`, `renpy.call`, `renpy.quit`, `renpy.pause`, `renpy.display_menu`, `renpy.scene`, `renpy.show`, `renpy.hide`, `renpy.with_statement`, `renpy.version`, `renpy.notify`, `renpy.random`, `renpy.config`, `persistent`, `Character`, `Transform`, `TintMatrix`, `Dissolve`, position constants (`right`, `left`, `center`, `truecenter`), transition constants (`dissolve`, `fade`).

Unimplemented `renpy.*` attributes return no-op stubs instead of raising errors.

## Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
```

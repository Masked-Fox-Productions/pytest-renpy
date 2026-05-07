# pytest-renpy

A pytest plugin for testing Ren'Py visual novel games.

## Status

Pre-implementation. See [docs/plans/](docs/plans/) for the design.

## Planned Features

**Layer 1 — Mock-based unit testing**
- Parse `.rpy` files and extract Python logic for testing
- Mock `renpy` namespace (jump, call, pause, persistent, etc.)
- Pytest fixtures for game store, command routing, markup parsing
- No Ren'Py SDK required at test time

**Layer 2 — Label-flow integration testing**
- Boot headless Ren'Py via IPC (subprocess + Unix socket)
- Navigate labels, simulate input, inspect store state
- Fast-forward pauses and tick loops
- Test full narrative sequences end-to-end

## Target Usage

```python
# Layer 1: unit test game logic
def test_command_routing(renpy_game):
    renpy_game.store.cmd_dict['base_cmds']['quit']['usable'] = True
    renpy_game.store.typing_message = "quit"
    
    with pytest.raises(JumpException):
        renpy_game.call('game_send')
    
    assert renpy_game.mock.quit_called


# Layer 2: integration test label flow
def test_fenton_intro(renpy_session):
    renpy_session.jump("fenton_initialize")
    renpy_session.advance_until("fenton_intro_new_user")
    
    log = renpy_session.get_terminal_log()
    assert "no previous session found" in log
```

## Development

Plans are in `docs/plans/`. Implementation will proceed in phases starting with Layer 1.

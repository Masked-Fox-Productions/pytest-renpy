# Plan: pytest-renpy Layer 2 — Label-Flow Integration Testing

## Goal

Extend `pytest-renpy` with an integration test mode that boots a minimal Ren'Py runtime, enabling tests that exercise actual label flow, screen state, and engine behavior — without requiring a display.

## Why Layer 2 Exists

Layer 1 tests Python logic in isolation. But Ren'Py games have behavior that only emerges from label flow:

- "When the player types 'start', does Fenton's intro actually proceed to question_1?"
- "Does `game_wait(5)` correctly block for 5 ticks before returning?"
- "After choosing 'scheduling', is the perk added AND the right label jumped to?"
- "Does input mode correctly disable commands and re-enable them after input?"

These require the actual Ren'Py call/jump/return machinery, the tick loop, and store mutations to happen in sequence — not just individual function calls.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 pytest (system Python)                │
│                                                      │
│  test_flow.py:                                       │
│    def test_fenton_intro(renpy_engine):              │
│        renpy_engine.jump("fenton_initialize")        │
│        renpy_engine.advance_until("fenton_intro_new_user")│
│        assert "no previous session found" in         │
│            renpy_engine.printed_lines                 │
└──────────────────────┬──────────────────────────────┘
                       │ IPC (subprocess + pipe or socket)
┌──────────────────────▼──────────────────────────────┐
│          Ren'Py Runtime (SDK's bundled Python)        │
│          SDL_AUDIODRIVER=dummy                        │
│          SDL_VIDEODRIVER=dummy                        │
│                                                      │
│  test_harness.rpy:                                   │
│    - Receives commands via IPC                       │
│    - Executes jumps/calls                            │
│    - Reports store state back                        │
│    - Fast-forwards pauses                            │
│    - Captures game_print output                      │
└─────────────────────────────────────────────────────┘
```

**Key architectural decision:** The test runner (pytest) and the Ren'Py engine run in separate processes. This is necessary because:
- Ren'Py requires its own bundled Python (3.9) with specific C extensions
- The engine's event loop is not designed to be embedded in another process
- Isolation prevents test state from leaking into the engine

## Components

### 1. Engine Runner (`engine.py`)

**Responsibility:** Launch a headless Ren'Py process, establish IPC, send commands, receive results.

```python
class RenpyEngine:
    def __init__(self, project_path, sdk_path):
        self.process = None
        self.connection = None
    
    def start(self):
        """Boot Ren'Py headlessly with the test harness loaded."""
    
    def jump(self, label):
        """Jump to a label and execute until it yields."""
    
    def call(self, label):
        """Call a label (pushes return stack)."""
    
    def advance(self, ticks=1):
        """Advance the game loop by N ticks."""
    
    def advance_until(self, label=None, condition=None, max_ticks=1000):
        """Advance until a label is reached or a condition on store is met."""
    
    def send_input(self, text):
        """Simulate typing + Enter (equivalent to game_send)."""
    
    def get_store(self, *vars):
        """Read current values of store variables."""
    
    def get_terminal_log(self):
        """Get current terminal_log contents."""
    
    def get_available_commands(self):
        """Get list of currently available commands."""
    
    def reset(self):
        """Reset game state to initial (faster than restarting process)."""
    
    def stop(self):
        """Terminate the engine process."""
```

### 2. Test Harness Game File (`_test_harness.rpy`)

A `.rpy` file injected into the game's directory during testing. It:
- Overrides the splashscreen label to enter test-control mode
- Listens for IPC commands (via a Python thread or polling in the tick loop)
- Executes requested operations inside the Ren'Py runtime
- Patches `renpy.pause()` to fast-forward (or skip entirely)
- Reports results back over IPC

```renpy
init -999 python:
    import threading
    import json
    
    _test_server = None
    _test_fast_forward = True
    
    # Monkey-patch pause to skip waits during testing
    _original_pause = renpy.pause
    def _test_pause(delay=None, *args, **kwargs):
        if _test_fast_forward:
            return
        return _original_pause(delay, *args, **kwargs)
    renpy.pause = _test_pause

label _test_harness_entry:
    # Control loop: receive and execute test commands
    python:
        while True:
            cmd = _test_receive_command()
            if cmd["type"] == "jump":
                renpy.jump(cmd["target"])
            elif cmd["type"] == "call":
                renpy.call(cmd["target"])
            elif cmd["type"] == "get_store":
                _test_send_response(...)
            elif cmd["type"] == "input":
                # Simulate keyboard input
                ...
```

### 3. IPC Protocol

**Transport:** Unix domain socket (fast, local-only, no port conflicts).

**Message format:** JSON lines (one JSON object per line, newline-delimited).

**Commands (pytest → engine):**

| Command | Payload | Response |
|---------|---------|----------|
| `jump` | `{"label": "foo"}` | `{"status": "yielded", "at_label": "...", "store_snapshot": {...}}` |
| `call` | `{"label": "foo"}` | Same as jump |
| `advance` | `{"ticks": N}` | `{"status": "yielded", "tick_count": N}` |
| `advance_until` | `{"label": "foo", "max_ticks": 1000}` | `{"status": "reached" or "timeout", "ticks_elapsed": N}` |
| `input` | `{"text": "hello"}` | `{"status": "processed", "jumped_to": "..."}` |
| `get_store` | `{"vars": ["x", "y"]}` | `{"values": {"x": ..., "y": ...}}` |
| `get_log` | `{}` | `{"terminal_log": [...]}` |
| `reset` | `{}` | `{"status": "reset"}` |
| `stop` | `{}` | (connection closes) |

**Serialization challenge:** Store variables may contain non-JSON-serializable objects (Ren'Py types, Python objects). The harness must handle:
- Primitives: pass through
- Lists/dicts: recursive serialize
- Ren'Py objects: `repr()` fallback
- Non-serializable: return `{"_type": "...", "_repr": "..."}` placeholder

### 4. Pytest Fixtures

| Fixture | Scope | Provides |
|---------|-------|----------|
| `renpy_engine` | session | Booted engine (expensive — one per test session) |
| `renpy_session` | function | Reset engine state between tests |

**Session-scoped engine:** Booting Ren'Py takes 2-5 seconds. We boot once per test session and reset state between tests (re-execute `init` blocks, clear store).

```python
@pytest.fixture(scope="session")
def renpy_engine(request):
    sdk_path = request.config.getoption("--renpy-sdk")
    project_path = request.config.getoption("--renpy-project")
    engine = RenpyEngine(project_path, sdk_path)
    engine.start()
    yield engine
    engine.stop()

@pytest.fixture
def renpy_session(renpy_engine):
    renpy_engine.reset()
    return renpy_engine
```

### 5. Fast-Forward System

Ren'Py's `renpy.pause()` and this game's `game_wait()` introduce real-time delays. In testing:
- `renpy.pause()` is patched to return immediately
- `game_wait()` ticks are fast-forwarded (tick_count incremented without real delay)
- Tests can opt into real-time with `@pytest.mark.renpy(realtime=True)` for timing-sensitive tests

### 6. Yield Points

The engine can't just "run a label and return" — labels contain jumps, calls, pauses, and user-input waits. The harness must define **yield points** where control returns to the test:

- `renpy.pause()` (the tick loop)
- `renpy.jump()` / `renpy.call()` that would transfer to a new label
- Input mode activation (game is waiting for player input)
- Label completion (fall-through to return)

When a yield point is hit, the harness serializes current state and sends it back over IPC. The test then decides what to do next.

## Implementation Phases

### Phase 1: IPC + Engine Boot (3-5 days)
- Write the Unix socket IPC protocol (JSON lines)
- Write the engine runner that launches Ren'Py headlessly
- Write the `_test_harness.rpy` control loop
- Verify: can boot, send "get_store", receive response, shut down cleanly
- Handle the SDL dummy driver environment

### Phase 2: Label Navigation (5-7 days)
- Implement `jump`, `call`, `advance` commands
- Patch `renpy.pause()` for fast-forwarding
- Implement yield-point detection (where does control return to test?)
- Handle Ren'Py's exception-based control flow (JumpException, CallException)
- Implement `advance_until` with label-matching and timeout
- Test against this game: jump to `fenton_initialize`, verify it reaches `fenton_intro_new_user`

### Phase 3: Input Simulation (3-5 days)
- Implement `input` command (equivalent to typing + Enter)
- Handle input mode (when game calls `take_input()`)
- Handle command routing (when game is in command-accept mode)
- Test: send "start" during Fenton's intro, verify jump to `fenton_intro_start`
- Test: send "scheduling" during question_1, verify perk is added

### Phase 4: State Inspection (2-3 days)
- Implement `get_store` with deep serialization
- Implement `get_log` for terminal_log inspection
- Implement `get_available_commands` helper
- Add assertion helpers: `assert_printed(text)`, `assert_at_label(label)`

### Phase 5: Reset + Multi-Test (3-5 days)
- Implement `reset` — restore store to post-init state without restarting engine
- Handle init-block re-execution ordering
- Verify tests don't leak state
- Run a full test suite (10+ tests) and verify isolation

### Phase 6: Pytest Integration + DX (2-3 days)
- Wire up as proper pytest fixtures
- Add `--renpy-sdk` and `--renpy-project` CLI options
- Add useful error messages (engine crash, timeout, label not found)
- Add `@pytest.mark.renpy_flow` marker for integration tests
- Distinguish from Layer 1 tests (both can coexist)

### Phase 7: Documentation + Packaging (2 days)
- Usage guide with examples
- Configuration reference
- Troubleshooting (common issues: SDL drivers, SDK path, timeout)
- Package alongside Layer 1 as optional dependency (`pip install pytest-renpy[integration]`)

## Example Tests (Target DX)

```python
# test_fenton_flow.py

def test_new_user_intro_sequence(renpy_session):
    """Fenton's intro prints the expected welcome messages."""
    renpy_session.jump("fenton_initialize")
    renpy_session.advance_until("fenton_intro_new_user")
    
    log = renpy_session.get_terminal_log()
    assert "no previous session found" in log
    assert "initializing new user..." in log


def test_start_command_proceeds_to_intro(renpy_session):
    """Typing 'start' advances past Fenton's greeting."""
    renpy_session.jump("fenton_intro_new_user")
    renpy_session.advance_until(condition=lambda s: "start" in s.get_available_commands())
    
    renpy_session.send_input("start")
    renpy_session.advance_until("fenton_intro_start")
    
    log = renpy_session.get_terminal_log()
    assert "initializing profile creation..." in log


def test_scheduling_perk_selection(renpy_session):
    """Choosing 'scheduling' grants the perk and advances to question 2."""
    renpy_session.jump("question_1")
    renpy_session.advance(ticks=5)  # let commands register
    
    renpy_session.send_input("scheduling")
    renpy_session.advance_until("question_2")
    
    perks = renpy_session.get_store("unsaved_data")["perks"]
    assert "scheduling" in perks


def test_input_mode_disables_commands(renpy_session):
    """When take_input is active, most commands are disabled."""
    renpy_session.jump("fenton_intro_start")
    renpy_session.advance_until(condition=lambda s: s.get_store("input_mode")["active"])
    
    store = renpy_session.get_store("cmd_dict")
    # save should be disabled during input mode
    assert store["base_cmds"]["save"]["usable"] == False
    # quit should remain usable
    assert store["base_cmds"]["quit"]["usable"] == True
```

## Technical Challenges

### 1. Ren'Py's Event Loop

Ren'Py's main loop (`renpy.main.main()`) is not designed to be paused and resumed externally. The harness must either:
- **Option A:** Run inside the event loop (harness is a Ren'Py label that polls for commands)
- **Option B:** Hijack the event loop (replace it with a test-controlled one)

**Recommendation:** Option A is safer and doesn't require engine internals. The harness label runs in the normal Ren'Py flow and communicates with the test process via IPC.

### 2. Exception-Based Control Flow

`renpy.jump()` raises an exception to unwind the call stack. When the harness label catches control back after a jump, it must re-enter the command loop. This means the harness must be a top-level exception handler:

```python
while True:
    cmd = receive_command()
    try:
        execute(cmd)
    except renpy.game.JumpException as e:
        send_response({"yielded_at": e.args[0]})
    except renpy.game.CallException as e:
        send_response({"called": e.args[0]})
```

### 3. The Tick Loop Problem

This game's `handle_tick` is a recursive `call` — it calls itself every 0.2s. In testing:
- Patch `renpy.pause(0.2)` to be instant
- But the recursion still consumes call stack depth
- May need to limit tick-based advancement or detect infinite loops
- `max_ticks` parameter on `advance_until` serves as the safety valve

### 4. Screen State

Ren'Py screens rebuild every frame. Testing screen state requires either:
- Querying the screen's display list (possible via `renpy.get_screen()`)
- Ignoring screen state entirely and testing only store + log

**Recommendation for Phase 1:** Ignore screens. Test store state and terminal_log. Screen testing can come later via `renpy.get_screen()` inspection.

### 5. Persistent Data

`persistent` survives across engine restarts. Tests must:
- Use a temp directory for persistent data (`config.savedir` override)
- Clear persistent between tests via `reset`

### 6. Cross-Python Communication

System Python (3.12, where pytest runs) must communicate with SDK Python (3.9, where Ren'Py runs). JSON over Unix sockets works regardless of Python version.

## Open Questions

1. **Should `advance_until` support regex matching on terminal_log?**
   - Useful for "advance until Fenton says X"
   - Could be a lambda condition on store, which is more general

2. **How to handle non-determinism?**
   - `fenton_initialize` uses `renpy.random.randint` for its progress bar
   - Seed the RNG in the harness, or accept non-deterministic flow and test postconditions

3. **Process lifecycle: one engine per session or per test?**
   - Per session (fast, requires good reset) vs. per test (slow, perfect isolation)
   - Recommendation: per session with reset, with option to mark tests as needing fresh engine

4. **How to handle engine crashes?**
   - If the Ren'Py process dies mid-test, the fixture should detect it, report the error, and optionally restart for subsequent tests

5. **Can we support breakpoint-style debugging?**
   - Developer calls `renpy_session.breakpoint("label_name")` → engine runs until label, then yields
   - Nice-to-have, not essential for v1

## Discoveries from Layer 1 Implementation

The following items were deferred or discovered during Layer 1 implementation and are relevant to Layer 2 planning.

### Label python: blocks (critical for minimum-viable-rpg)

minimum-viable-rpg defines 18 utility functions (combat, inventory, healing, condition checks) inside `label init_utils: / python:` blocks. These are invisible to Layer 1's init-block extraction — they only exist after the engine executes the label. Layer 2 must execute label python: blocks to make these functions available. This is the most common pattern for complex game logic in normal Ren'Py projects.

Similarly, minimum-viable-rpg puts all 19 `default` statements inside `label start:`, not at top level. Layer 2's store initialization must account for defaults declared within labels.

### default inside labels

Both `default` inside labels and variables set via `$ var = value` inside labels are Layer 2 concerns. The parser currently extracts top-level defaults only. Layer 2 needs to handle label-scoped defaults as part of label execution.

### Multi-line define/default expressions

The Layer 1 parser extracts `define` and `default` as single-line statements. kid-and-king has a multi-line `default BOOKS = { ... }` spanning 6 lines that fails to parse. Layer 2 could either:
- Extend the parser with continuation-line support (look for unclosed brackets)
- Let the engine handle these natively (since Layer 2 runs real Ren'Py)

The engine-native approach is simpler and more correct, since Ren'Py's own parser handles arbitrary Python expressions in define/default.

### Ren'Py built-in namespaces: gui, build, config

All three reference projects have `gui.rpy`, `screens.rpy`, and `options.rpy` that reference Ren'Py-internal namespaces (`gui`, `build`, `Borders`, `_()` translation function). These fail in Layer 1's mock but will work natively in Layer 2. Layer 2 should verify that these files load cleanly.

### terminalgame's Python 3.12 syntax error

terminalgame's `display.rpy` has a `global` declaration after assignment in `does_show_character()` — valid in Ren'Py's Python 2-style runtime but rejected by Python 3.12. Since Layer 2 runs inside Ren'Py's bundled Python (3.9), this code should work correctly. This is a case where Layer 2 would succeed where Layer 1 fails.

### display_menu as a core testing surface

`renpy.display_menu()` is the programmatic menu API used by both kid-and-king and minimum-viable-rpg. Layer 2 needs robust menu interaction — send a choice by index or text match, inspect available options. Layer 1 mocks it to return the first option; Layer 2 should support test-driven selection.

### Scene management APIs in game logic

minimum-viable-rpg calls `renpy.scene()`, `renpy.show()`, `renpy.hide()`, `renpy.with_statement()` from Python code. Layer 2's yield-point detection should account for these — they're not control flow (don't raise exceptions) but they modify display state that tests may want to inspect.

### Exception propagation through globals() dispatch

terminalgame's `check_for_commands()` dispatches via `globals()[destination](message)`. When the destination function raises (e.g., `quit_command` raises `QuitException`), execution halts and the exception propagates through the dispatch chain. Layer 2's exception handling must correctly attribute these exceptions to the originating function, not to `check_for_commands` itself.

### sys.path for .py file imports

kid-and-king uses `from utils import *` in `init python:` to import `game/utils.py`. Layer 1 handles this via sys.path scoping during exec. Layer 2 inherits this from Ren'Py natively (the engine adds `game/` to sys.path), but the test harness should verify that imported .py modules are also reset-able between tests.

## Dependencies on Layer 1

Layer 2 reuses from Layer 1:
- The `.rpy` parser (for understanding project structure, listing labels)
- The mock_renpy types (for deserializing store snapshots)
- The pytest plugin registration (shared `conftest.py` fixtures)

Layer 2 does NOT reuse:
- The mock execution model (Layer 2 uses the real engine)
- The store fixture (Layer 2 uses the real store via IPC)

## Success Criteria

- [ ] Can run full narrative sequences (boot → Fenton intro → character creation → perk selection)
- [ ] Tests execute in < 500ms each (after session boot)
- [ ] Engine boot takes < 5 seconds
- [ ] State resets between tests with no leakage
- [ ] Useful error messages when labels don't exist or engine crashes
- [ ] Works with any Ren'Py 8.x project (not hardcoded to this game)
- [ ] Coexists with Layer 1 tests (both run in same `pytest` invocation)

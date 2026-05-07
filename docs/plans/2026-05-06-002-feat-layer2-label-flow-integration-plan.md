---
title: "feat: Layer 2 — Label-Flow Integration Testing via Headless Engine"
type: feat
status: active
date: 2026-05-06
origin: docs/plans/layer2-label-flow-integration.md
---

# feat: Layer 2 — Label-Flow Integration Testing via Headless Engine

## Overview

Extend `pytest-renpy` with an integration test mode that boots a headless Ren'Py subprocess, communicates over IPC, and enables tests that exercise actual label flow, store mutations, menu interaction, and tick-loop advancement — without requiring a display.

## Problem Frame

Layer 1 tests Python logic in isolation by extracting `init python:` blocks and running them under a mock `renpy` namespace. But most Ren'Py game behavior emerges from **label flow** — the engine's jump/call/return machinery, tick loops, input gating, and store mutations that happen in sequence across labels. Critical patterns that Layer 1 cannot reach:

- **Functions defined in label `python:` blocks** — minimum-viable-rpg defines 18 utility functions inside `label init_utils:` / `python:`. These are invisible to Layer 1's init-block extraction. This is the most common pattern for complex game logic in real Ren'Py projects.
- **`default` inside labels** — minimum-viable-rpg puts all 19 defaults inside `label start:`, not at top level.
- **Narrative flow assertions** — "Does typing 'start' at Fenton's intro actually jump to `fenton_intro_start`?" requires the engine's call stack, tick loop, and input routing to execute.
- **Menu interaction** — kid-and-king and minimum-viable-rpg use `renpy.display_menu()` to build dynamic menus from game state. Testing menu-driven flow requires the engine to present options and accept a choice.
- **Tick-loop mechanics** — terminalgame's `handle_tick` is a recursive `call` (every 0.2s). Testing time-dependent behavior (e.g., `game_wait(5)` blocking for 5 ticks) requires the engine's pause/advance machinery.
- **Multi-line define/default expressions** — kid-and-king has a 6-line `default BOOKS = { ... }` that the Layer 1 parser can't handle. The real engine parses these natively.
- **Ren'Py built-in namespaces** — `gui`, `build`, `config`, `Borders()`, `_()` all fail in Layer 1's mock but work natively in the engine.

(see origin: `docs/plans/layer2-label-flow-integration.md`, "Why Layer 2 Exists" and "Discoveries from Layer 1 Implementation")

## Requirements Trace

- R1. Boot a headless Ren'Py process (SDL dummy drivers, no display) and establish bidirectional IPC
- R2. Navigate label flow: `jump(label)`, `call(label)`, `advance(ticks)`, `advance_until(label|condition)`
- R3. Mutate store state from tests (`set_store`) to enable game-specific input adapter patterns (e.g., set `typing_message` then trigger `game_send`)
- R4. Interact with menus: inspect options from `renpy.display_menu()`, select by index or text match
- R5. Inspect engine state: read store variables, terminal log, available commands via IPC
- R6. Fast-forward time: patch `renpy.pause()` to skip real-time delays in tests
- R7. Isolate test state: fresh engine process per test (v1 default). Session-scoped reuse with in-process reset is a stretch goal, contingent on spike results
- R8. Provide pytest fixtures (`renpy_engine`, `renpy_session`) that coexist with Layer 1 fixtures
- R9. Preserve Ren'Py's exception-based control flow (`JumpException`, `CallException`) and report navigation errors over IPC
- R10. Serialize store state across Python version boundary (system Python 3.12 ↔ SDK Python 3.9)
- R11. Work with any Ren'Py 8.x project, not hardcoded to a specific game
- R12. Engine boot completes in < 5 seconds per test; command latency and navigation after boot complete in < 500ms

## Scope Boundaries

- No screen rendering or display-list inspection (test store state and log, not visual output)
- No audio playback or media testing
- No save/load cycle testing (persistent data is isolated to temp dir, but save file round-trips are out of scope)
- No `python early:` block testing (requires engine internals beyond the IPC surface)
- No CI/CD integration (SDK path configuration is left to the user)

### Deferred to Separate Tasks

- Screen state inspection via `renpy.get_screen()`: future Layer 2 extension once core flow testing is stable
- Breakpoint-style debugging (`renpy_session.breakpoint("label_name")`): nice-to-have, not essential for v1
- Regex matching on terminal_log in `advance_until`: lambda conditions on store are more general and sufficient

## Context & Research

### Relevant Code and Patterns

**Layer 1 components reused by Layer 2:**
- `src/pytest_renpy/rpy_parser.py` — parser used to list labels for validation and project structure understanding
- `src/pytest_renpy/mock_renpy/store.py` — `StoreNamespace` may inform deserialized store representation on the pytest side
- `src/pytest_renpy/plugin.py` — shared plugin registration; Layer 2 adds `--renpy-sdk` option alongside existing `--renpy-project`
- `src/pytest_renpy/__init__.py` — exception types shared across both layers

**Layer 1 components NOT reused:**
- Mock execution model (Layer 2 uses the real engine)
- Store fixture (Layer 2 reads the real store via IPC)
- Loader (Layer 2 doesn't exec init blocks — the engine does)

**Reference project patterns critical to Layer 2 design:**

| Pattern | Terminal Game | Kid & King | Min. RPG |
|---------|-------------|-----------|----------|
| Menu/Choice | Command dispatch dict | `renpy.display_menu()` | `renpy.display_menu()` |
| Label entry | Recursive tick loop | Sequential label jumps | Init chain + sequential |
| Input handling | `input_mode` flags, command lookup | Direct menu return | Direct menu return |
| State mutation | Global dicts (`terminal_log`, `cmd_dict`) | Reader objects | Persistent dicts (`LOCATIONS`, `hero_stats`) |
| Dynamic dispatch | `globals()[destination](message)` | `renpy.jump(f'talk_to_{name}')` | `renpy.jump(f'init_{tag}')` |
| Utility functions | `init python:` blocks | Class defs in `init python:` | **`label init_utils:` python block** |

### Institutional Learnings

From `docs/discovered-bugs.md`:
- terminalgame's `display.rpy` has a `global` declaration after assignment — valid in Ren'Py's Python 2-style runtime but rejected by Python 3.12. Layer 2 runs inside Ren'Py's bundled Python (3.9), so this works correctly — a case where Layer 2 succeeds where Layer 1 fails.
- terminalgame's `keyboard.rpy` exception propagation through `globals()` dispatch — Layer 2's harness must correctly handle exceptions that originate from destination functions called via dynamic dispatch.

## Key Technical Decisions

- **Separate processes, IPC via Unix domain socket:** The test runner (pytest, system Python 3.12) and the Ren'Py engine (SDK Python 3.9) run in separate processes. This is necessary because Ren'Py requires its own bundled Python with specific C extensions, and its event loop is not designed to be embedded. Unix domain sockets are fast, local-only, require no port allocation, and work regardless of Python version. JSON lines (newline-delimited JSON) is the wire format — simple, debuggable, cross-version compatible.

- **Trampoline-based label execution:** The harness cannot catch `JumpException`/`CallException` and continue — doing so prevents Ren'Py from actually executing the target label. Instead, the harness uses a **trampoline pattern**: when a `jump` command arrives, the harness allows the exception to propagate to Ren'Py's own exception handler (which performs the actual label transfer), and a **yield-point hook** (monkey-patched into `renpy.pause`, `renpy.display_menu`, or the interaction cycle) sends state back to the IPC client when the engine next yields. The harness entry label is re-entered via a trampoline label that Ren'Py jumps to when execution reaches a yield point. The exact mechanism (trampoline labels, `call_in_new_context`, or interaction-cycle callbacks) is the primary question the control-flow spike (Unit 0) must answer.

- **Yield-point architecture:** The engine can't "run a label and return" — labels contain jumps, calls, pauses, and input waits. Yield points are where the engine naturally pauses and control can return to the test: `renpy.pause()` calls, `renpy.display_menu()` invocations, and interaction boundaries. The harness instruments these yield points (via monkey-patching or callbacks) to serialize current state and send it back over IPC, then block waiting for the next command. The key constraint: yield-point instrumentation must preserve the engine's interaction cycle, not bypass it.

- **Fresh-process isolation by default (v1):** Booting Ren'Py takes 2-5 seconds. In v1, each test gets a fresh engine process for perfect isolation. Session-scoped reuse with in-process reset is a **stretch goal** — restoring store state inside a running Ren'Py process requires re-executing init blocks and clearing label-scoped state through APIs that may not be cleanly available. The spike (Unit 0) will evaluate whether session-scoped reuse is feasible; if not, the plan proceeds with fresh-process isolation and optimizes boot time instead. Tests can opt into session scope via `@pytest.mark.renpy(reuse_engine=True)` if the spike proves reuse viable.

- **Fast-forward via interaction-cycle control:** `renpy.pause()` cannot simply be patched to return immediately — that removes the yield point the harness depends on. Instead, the monkey-patch must preserve the interaction/yield semantics while eliminating wall-clock delay. The spike (Unit 0) will determine the right mechanism: patching the delay argument to 0 while preserving the interaction cycle, using `renpy.call_in_new_context`, or another approach. Tests can opt into real-time with `@pytest.mark.renpy(realtime=True)`.

- **Graceful serialization with fallback:** Store variables may contain non-JSON-serializable Ren'Py objects. The harness serializes primitives, lists, and dicts directly; falls back to `{"_type": "ClassName", "_repr": "repr(obj)"}` for unserializable objects. This keeps the IPC protocol simple while still allowing store inspection.

- **Temp directory for persistent data:** `config.savedir` is overridden to a temp directory during testing. This isolates persistent data between test sessions and prevents tests from corrupting real save files.

- **RNG seeding for determinism:** The harness seeds `renpy.random` with a fixed value (0) on boot and on each reset, matching Layer 1's approach. Tests can override via `renpy_session.seed_random(N)`.

## Open Questions

### Resolved During Planning

- **Should `advance_until` support regex on terminal_log?** No — lambda conditions on store are more general. `advance_until(condition=lambda s: "text" in s.get("terminal_log", []))` handles this.

- **Process lifecycle: per-session or per-test?** Fresh-process per test in v1 for perfect isolation (see Key Technical Decisions). Session-scoped reuse is a stretch goal pending spike results.

- **How to handle engine crashes?** The fixture monitors the subprocess. If the process dies mid-test, it detects via broken pipe / process exit, raises `EngineError` with stderr output. Since v1 uses fresh processes per test, subsequent tests simply start a new engine.

- **Harness approach: inside event loop or hijack?** Inside event loop. The harness runs as a normal Ren'Py label. It does NOT catch jump/call exceptions — it allows them to propagate to Ren'Py's own handler so labels actually execute. Control returns to the harness via yield-point hooks instrumented into `renpy.pause`, `renpy.display_menu`, and the interaction cycle. The exact mechanism is the subject of the control-flow spike (Unit 0).

- **Input simulation scope?** Generic text input simulation (setting `typing_message`, calling `game_send()`) is terminalgame-specific, not a general Ren'Py pattern. R3 (`send_input`) is narrowed to mean "inject text into the engine's text input API" — if Ren'Py has a programmatic input API, the harness uses it; otherwise, v1 limits generic input to menu selection (R4) and provides a game-specific adapter hook for projects like terminalgame that use custom input dispatch. R11 ("any Ren'Py 8.x project") applies to label navigation, store inspection, and menu interaction — not to custom input routing.

### Deferred to Implementation

- **Control-flow mechanism for label execution and yield-back:** The central unknown. The spike (Unit 0) must determine how to: (a) trigger label execution that Ren'Py processes normally, (b) yield control back to the IPC client at interaction boundaries. Candidates: trampoline labels, `renpy.call_in_new_context`, interaction-cycle callbacks, or a controlled script runner. The chosen mechanism shapes Units 3-7.
- **`advance` semantics and the interaction cycle:** `advance(ticks=N)` must process N Ren'Py interaction cycles while eliminating wall-clock delay. Simply calling `renpy.pause(0)` in a loop does not process interactions, timers, input, menus, or label flow. The spike must determine how to drive the interaction cycle forward without real-time pauses — possibly via `renpy.exports.pause(0)` (which may preserve the interaction yield), a callback-based approach, or direct interaction-loop manipulation.
- **Call stack depth under recursive tick loops:** terminalgame's `handle_tick` calls itself recursively. `advance(ticks=1000)` may hit Python's recursion limit. May need to detect and break recursion or limit tick-based advancement. `max_ticks` parameter serves as a safety valve.
- **Reset feasibility in a live Ren'Py process:** Ren'Py's init/default behavior is tied to engine initialization and script state. Re-executing init blocks and clearing the store inside a running process may not be available as a clean API. The spike will evaluate whether this is feasible. If not, session-scoped reuse is dropped from v1 and fresh-process isolation is the only mode.
- **Menu interaction timing:** When `renpy.display_menu()` is called inside the engine, the harness must intercept it before it blocks for user input. The exact interception point (monkey-patch `renpy.display_menu` vs. intercept at the interaction layer) depends on Ren'Py internals.
- **Thread safety of IPC polling:** The harness either polls for IPC commands synchronously (simple, blocks the engine) or uses a background thread (complex, potential thread-safety issues with Ren'Py's single-threaded design). Implementation will determine the simpler viable approach.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌──────────────────────────────────────────────────────────┐
│                  pytest (system Python 3.12)               │
│                                                           │
│  test_flow.py:                                            │
│    def test_fenton_intro(renpy_session):                  │
│        renpy_session.jump("fenton_initialize")            │
│        renpy_session.advance_until("fenton_intro_new_user")│
│        assert "no previous session found" in              │
│            renpy_session.get_terminal_log()                │
│                                                           │
│  ┌───────────────────────────────────────────────┐        │
│  │  RenpyEngine                                  │        │
│  │  - start() → subprocess.Popen(sdk_python,     │        │
│  │              env={SDL_VIDEODRIVER=dummy, ...})  │        │
│  │  - jump/call/advance/input → JSON command     │        │
│  │  - receive ← JSON response with store snapshot │        │
│  │  - reset() → reinitialize without restart      │        │
│  │  - stop() → terminate subprocess               │        │
│  └───────────────┬───────────────────────────────┘        │
└──────────────────┼────────────────────────────────────────┘
                   │ Unix domain socket (JSON lines)
┌──────────────────┼────────────────────────────────────────┐
│  Ren'Py Runtime  │  (SDK Python 3.9, headless)            │
│                  ▼                                        │
│  _test_harness.rpy:                                       │
│    init -999 python:                                      │
│      - Monkey-patch renpy.pause() → preserve interaction  │
│        cycle but eliminate wall-clock delay; at each       │
│        yield point, send state over IPC and block for     │
│        next command                                       │
│      - Monkey-patch renpy.display_menu() → IPC intercept  │
│      - Seed renpy.random                                  │
│      - Connect to IPC socket                              │
│                                                           │
│    label splashscreen: → jump _test_harness_entry          │
│                                                           │
│    label _test_harness_entry:                              │
│      # Command loop — blocks on IPC, dispatches commands  │
│      # For jump/call: lets exception propagate to Ren'Py  │
│      #   so the label actually executes. Control returns  │
│      #   to IPC via yield-point hooks (patched pause/menu)│
│      # For get_store/ping: responds directly              │
│      # Exact mechanism determined by spike (Unit 0)       │
└───────────────────────────────────────────────────────────┘
```

**Command/Response Protocol (JSON lines):**

```
→ {"cmd": "jump", "label": "fenton_initialize"}
← {"status": "yielded", "at_label": "fenton_intro_new_user", "ticks": 42}

→ {"cmd": "get_store", "vars": ["terminal_log", "cmd_dict"]}
← {"status": "ok", "values": {"terminal_log": [...], "cmd_dict": {...}}}

→ {"cmd": "set_store", "vars": {"typing_message": "start"}}
← {"status": "ok"}

→ {"cmd": "menu_select", "index": 0}
← {"status": "selected", "choice": "scheduling", "jumped_to": "question_2"}

→ {"cmd": "stop"}
← {"status": "stopping"}
```

**Yield-point state machine:**

```
                    ┌─────────────┐
          ┌────────►│  WAITING_CMD │◄──────────────┐
          │         └──────┬──────┘                │
          │                │ receive command        │
          │                ▼                        │
          │         ┌─────────────┐                │
          │         │  EXECUTING  │                │
          │         └──────┬──────┘                │
          │                │                        │
          │    ┌───────────┼───────────┐            │
          │    ▼           ▼           ▼            │
     ┌─────────┐   ┌───────────┐  ┌────────┐      │
     │  PAUSE  │   │   JUMP/   │  │  INPUT │      │
     │ (yield) │   │   CALL    │  │  WAIT  │      │
     └────┬────┘   │  (yield)  │  │ (yield)│      │
          │        └─────┬─────┘  └───┬────┘      │
          │              │            │            │
          └──────────────┴────────────┘            │
                         │ send response           │
                         └─────────────────────────┘
```

## Output Structure

```
src/pytest_renpy/
  engine/
    __init__.py           # RenpyEngine class (subprocess + IPC client)
    ipc.py                # Socket client: connect, send_command, receive_response
    protocol.py           # Command/response dataclasses, serialization helpers
  _test_harness.rpy       # Injected into game dir at test time (template)
  plugin.py               # Modified: adds --renpy-sdk option
  fixtures.py             # Modified: adds renpy_engine, renpy_session fixtures

tests/
  test_engine.py          # Engine boot, IPC, shutdown tests
  test_ipc.py             # Protocol serialization, socket communication tests
  test_harness.py         # Harness behavior tests (may require SDK)
  test_integration_fixtures.py  # renpy_engine/renpy_session fixture tests

examples/
  terminalgame/
    test_flow.py           # Label-flow integration tests
  kid-and-king/
    test_flow.py           # Menu interaction integration tests
  minimum-viable-rpg/
    test_flow.py           # Label-python-block integration tests
```

## Implementation Units

### Phase 0: Spike (Gate for All Subsequent Units)

- [ ] **Unit 0: Ren'Py Control-Flow Spike**

**Goal:** Prove the three core assumptions that the rest of the plan depends on, using a tiny fixture game (not a real project). This unit is a mandatory gate — Units 1-10 should not begin until the spike validates a viable control-flow mechanism.

**Requirements:** R1, R2, R6, R7, R9

**Dependencies:** None

**Files:**
- Create: `spike/fixture_game/game/script.rpy` (minimal game: two labels, a store variable, a `renpy.pause()`, a `renpy.display_menu()`)
- Create: `spike/harness_spike.rpy` (minimal harness exploring control-flow candidates)
- Create: `spike/driver.py` (Python script that launches the engine and communicates over IPC)
- Create: `spike/README.md` (documents findings and chosen approach)

**Approach:**

The spike must prove three things against the fixture game:

1. **Jump into a label and observe store mutation.** Send a command that causes the engine to jump to a label. The label sets `store.x = 42`. After the label executes, read `store.x` over IPC and verify it equals 42. This proves that the control-flow mechanism allows labels to actually run (not just report the target).

2. **Yield back to IPC after a pause/menu/input point.** After the label runs and hits a `renpy.pause()` or `renpy.display_menu()`, the harness must send state back over IPC and block for the next command. This proves that yield-point instrumentation works without breaking the interaction cycle.

3. **Reset or restart cleanly between two tests.** Run a sequence: jump to label A (sets `store.x = 42`), then either reset state or restart the process, then verify `store.x` is back to its default. This determines whether session-scoped reuse is feasible or if fresh-process isolation is the only viable v1 approach.

**Candidate mechanisms to evaluate:**
- **Trampoline labels:** After the target label yields (via patched `renpy.pause`), the patched pause jumps to a trampoline label that re-enters the IPC command loop. Concern: may not work if `renpy.pause` can't raise `JumpException` in all contexts.
- **`renpy.call_in_new_context`:** Executes a label in a new context. May provide natural yield-back when the context completes. Concern: may not share the main store context.
- **Interaction-cycle callback:** Register a callback in the interaction cycle that checks for IPC commands on each tick. Concern: depends on engine internals.
- **`renpy.pause(0)` semantics:** Test whether `renpy.pause(0)` processes one interaction cycle without wall-clock delay. If so, it can serve as the advance primitive.

**Test scenarios:**
- Spike test 1: boot the fixture game headlessly (SDL dummy drivers), verify the harness connects over IPC and responds to `ping`
- Spike test 2: send `jump` to `label set_x`, verify `store.x` was mutated (label actually executed, not just reported)
- Spike test 3: label with `renpy.pause()` — verify that after the pause, state is sent over IPC and the next command is received
- Spike test 4: label with `renpy.display_menu()` — verify menu options are sent over IPC and a selection can be returned
- Spike test 5: after modifying state, reset/restart and verify state is clean

**Verification:**
- At least one control-flow mechanism demonstrably works for all three goals
- A `spike/README.md` documents: which mechanisms were tested, which worked, which failed and why, and the recommended approach for the full implementation
- The spike informs updates to Units 1-10 (particularly Units 3, 4, 6, and 7)

**Exit criteria — what determines the plan update:**
- If trampoline/callback approach works → Units 3-7 proceed with that mechanism, session-scoped reuse may be viable
- If only `call_in_new_context` works → Units 3-7 adapt to context-based execution, test store sharing
- If no in-process yield-back works → consider alternative architectures (e.g., one-shot label execution per command, or a Ren'Py-side test runner that reads a test script)
- If reset is not feasible → R7 is dropped, v1 uses fresh-process per test only, Unit 7 becomes "process lifecycle optimization"

---

### Phase 1: IPC Foundation

- [ ] **Unit 1: IPC Protocol and Socket Communication**

**Goal:** Implement the JSON-lines protocol layer and Unix domain socket client/server, testable independently of Ren'Py.

**Requirements:** R1, R10

**Dependencies:** None

**Files:**
- Create: `src/pytest_renpy/engine/__init__.py`
- Create: `src/pytest_renpy/engine/protocol.py`
- Create: `src/pytest_renpy/engine/ipc.py`
- Test: `tests/test_ipc.py`

**Approach:**
- `protocol.py` defines command and response dataclasses: `Command(cmd, **payload)` and `Response(status, **data)`. Provides `serialize(obj) -> str` (JSON line) and `deserialize(line) -> dict` with the fallback serialization for non-JSON types (`{"_type": "...", "_repr": "..."}`)
- `ipc.py` implements `IPCClient` (pytest side) and `IPCServer` (harness side). Client: `connect(socket_path)`, `send_command(cmd) -> response`, `close()`. Server: `bind(socket_path)`, `accept()`, `receive_command() -> cmd`, `send_response(response)`, `close()`
- Socket path uses `tempfile.mkdtemp()` to avoid conflicts between parallel test sessions
- Both sides handle partial reads (buffering until newline), connection drops (raise `ConnectionError`), and timeouts (configurable, default 30s)
- The server side must be compatible with Python 3.9 (Ren'Py's bundled Python) — no f-strings with `=` debug format, no walrus operator in complex expressions, no `match` statements
- The client side is system Python 3.12+

**Patterns to follow:**
- JSON lines protocol (newline-delimited JSON) — widely used, simple to debug
- `socket.AF_UNIX` for local-only IPC with no port conflicts

**Test scenarios:**
- Happy path: client sends a JSON command, server receives and deserializes it correctly
- Happy path: server sends a JSON response, client receives and deserializes it correctly
- Happy path: multiple command/response round-trips on the same connection
- Happy path: serialize a dict with nested primitives (str, int, float, bool, None, list, dict) — round-trips correctly
- Edge case: serialize a non-JSON object (custom class instance) — produces `{"_type": "ClassName", "_repr": "..."}`
- Edge case: serialize a dict containing a mix of serializable and non-serializable values — serializable values pass through, non-serializable use fallback
- Edge case: very large payload (10KB+ JSON) — buffered read handles correctly
- Error path: client sends to a closed server — raises `ConnectionError`
- Error path: server receives malformed JSON — raises or returns a structured error
- Error path: read timeout exceeded — raises `TimeoutError`
- Integration: two processes communicate over a real Unix socket (subprocess test)

**Verification:**
- Protocol round-trips all JSON-serializable Python types correctly
- Fallback serialization handles arbitrary objects without crashing
- Client and server can communicate across processes (not just in-process)

---

- [ ] **Unit 2: Engine Runner (Subprocess Management)**

**Goal:** Launch a headless Ren'Py process with the test harness injected, establish IPC connection, and manage subprocess lifecycle.

**Requirements:** R1, R6, R11, R12

**Dependencies:** Unit 1 (IPC protocol and socket communication)

**Files:**
- Create: `src/pytest_renpy/engine/runner.py`
- Test: `tests/test_engine.py`

**Approach:**
- `RenpyEngine` class manages the subprocess lifecycle: `start()`, `stop()`, `is_alive()`
- `start()` does the following in order:
  1. Creates a **temp project root** containing a copy (or symlink) of the project's `game/` directory. Ren'Py expects a project root with `game/` as a subdirectory, so the runner creates `tmp_root/game/` — not just a bare copy of the game dir. The harness .rpy file is placed in `tmp_root/game/`, not the original. If the engine crashes or cleanup fails, the user's project is untouched. The temp root is the `project_path` passed to Ren'Py
  2. Copies `_test_harness.rpy` into the temp game directory
  3. Creates a temp directory for persistent/save data (`config.savedir` override)
  4. Creates the Unix socket and starts listening
  5. Launches `subprocess.Popen([sdk_python, renpy_main, temp_project_path], env={SDL_VIDEODRIVER: "dummy", SDL_AUDIODRIVER: "dummy", RENPY_TEST_SOCKET: socket_path, RENPY_TEST_SAVEDIR: temp_dir})`
  6. Waits for the harness to connect (with timeout)
  7. Sends a `ping` command and waits for `pong` response to verify the engine is ready
- `stop()` sends a `stop` command, waits for process termination (with timeout), cleans up all temp directories (game copy, save dir, socket)
- `is_alive()` checks subprocess poll status
- Engine crash detection: if `process.poll()` returns non-None during a command, capture stderr and raise `EngineError` with the error output
- The SDK Python path is resolved from `--renpy-sdk` option: looks for `lib/py3-linux-x86_64/python` (or platform equivalent) within the SDK directory
- Environment variables passed to the subprocess configure headless mode and IPC

**Execution note:** Start with a test that verifies the engine can boot and respond to `ping` — this validates the entire subprocess + IPC + harness stack before adding navigation commands.

**Patterns to follow:**
- `subprocess.Popen` with explicit env, stdin/stdout/stderr configuration
- Context manager protocol (`__enter__`/`__exit__`) for automatic cleanup

**Test scenarios:**
- Happy path: engine boots with valid SDK and project paths, responds to ping, shuts down cleanly
- Happy path: engine process environment includes SDL dummy drivers
- Happy path: temp copy of game directory is created; harness .rpy is placed in the copy, not the original project
- Happy path: original project directory is unmodified after start and stop
- Happy path: temp save directory is created on start and cleaned up on stop
- Edge case: engine boot timeout — raises `EngineError` with descriptive message after N seconds
- Edge case: stop() called when engine is already dead — no error, cleans up resources
- Edge case: engine crashes — temp directories are still cleaned up (finally/atexit)
- Error path: invalid SDK path — raises `EngineError` explaining the SDK was not found
- Error path: invalid project path — raises `EngineError` explaining the project directory is invalid
- Error path: engine process crashes during start — captures stderr, raises `EngineError`
- Error path: engine process dies mid-session — detected on next command, raises `EngineError` with stderr

**Verification:**
- Engine boots in under 5 seconds with a real Ren'Py project
- Process cleanup is complete (no orphan processes, no leftover files)
- Error messages include actionable information (SDK path tried, stderr output)

---

- [ ] **Unit 3: Test Harness (.rpy File)**

**Goal:** Create the `_test_harness.rpy` file that runs inside the Ren'Py process, connects to the IPC socket, and dispatches test commands within the engine's event loop.

**Requirements:** R1, R6, R9, R10

**Dependencies:** Unit 0 (spike determines the control-flow mechanism), Unit 1 (protocol), Unit 2 (engine runner provides the socket path via env var)

**Files:**
- Create: `src/pytest_renpy/_test_harness.rpy`
- Test: `tests/test_harness.py`

**Approach:**
- Written as a `.rpy` file compatible with Ren'Py's Python 3.9 runtime
- `init -999 python:` block runs before all game init blocks:
  - Reads `RENPY_TEST_SOCKET` from `os.environ` to find the socket path
  - Reads `RENPY_TEST_SAVEDIR` from `os.environ` and overrides `config.savedir`
  - Monkey-patches `renpy.pause()` using the mechanism validated by the spike — must preserve the interaction cycle while eliminating wall-clock delay, and send state over IPC at each yield point
  - Monkey-patches `renpy.display_menu()` to send menu options over IPC and wait for a selection command
  - Seeds `renpy.random` with 0
  - Connects to the Unix socket
- `label splashscreen:` jumps to `_test_harness_entry` (overrides any game splashscreen)
- `label _test_harness_entry:` is the IPC command loop:
  - Blocks on socket waiting for a command
  - Dispatches the command (jump, call, advance, get_store, menu_select, reset, stop)
  - **Does NOT catch JumpException/CallException** — navigation exceptions must propagate to Ren'Py so labels actually execute
  - Control returns to the IPC command loop via yield-point hooks (the mechanism proven by the spike)
- Command dispatch details:
  - `jump`: triggers label execution via the spike-validated mechanism. The label runs to completion or until a yield point (pause/menu), at which point the yield-point hook sends state over IPC and blocks for the next command
  - `call`: similar to jump but uses Ren'Py's call stack
  - `advance`: drives N interaction cycles forward using the spike-validated mechanism. NOT a no-op loop — must actually process the interaction cycle
  - `advance_until`: repeatedly advances (up to `max_ticks`) until the specified label is reached or a condition on store is met
  - `get_store`: reads requested variables from the store namespace, serializes with fallback
  - `get_log`: reads `terminal_log` (or equivalent) from store
  - `menu_select`: responds to a `menu_waiting` state with the selected option
  - `reset`: if spike proves feasible, re-initializes store state; otherwise, signals the pytest side to restart the process
  - `stop`: closes the socket and calls `renpy.quit()`

**Technical design:**

> *The pseudo-code from the original sketch (catch JumpException and continue) is known to be wrong — catching the exception prevents the label from executing. The actual implementation must use the mechanism validated by the spike (Unit 0). The sketch below shows the intent, not the mechanism:*

```
# INTENT (not implementation):
# 1. Test sends: {"cmd": "jump", "label": "set_x"}
# 2. Harness triggers jump → Ren'Py executes label set_x
#    (label sets store.x = 42, then hits renpy.pause())
# 3. Yield-point hook fires at the pause:
#    - Sends {"status": "yielded", "at_label": "...", "store": {"x": 42}}
#    - Blocks waiting for next command
# 4. Test receives response, asserts store.x == 42
#
# The critical constraint: step 2 must let Ren'Py process
# the jump normally. The harness cannot swallow the exception.
```

**Patterns to follow:**
- Ren'Py's own test framework uses `init -999` for early initialization
- Exception-based control flow is the standard Ren'Py pattern (validated in Layer 1 design)

**Test scenarios:**
- Happy path: harness connects to socket on boot and responds to `ping` with `pong`
- Happy path: `jump` command causes the target label to **actually execute** (store mutation observed)
- Happy path: `call` command executes the target label and preserves the return stack
- Happy path: after label execution hits a yield point (pause/menu), state is sent over IPC
- Happy path: `get_store` with valid variable names returns their current values
- Happy path: `get_store` with a non-existent variable returns `None`
- Happy path: `advance` with ticks=5 processes 5 interaction cycles (not just a no-op loop)
- Happy path: `stop` terminates the engine cleanly
- Edge case: `get_store` for a variable containing a non-serializable Ren'Py object — returns fallback representation
- Edge case: `advance_until` with `max_ticks` reached — returns timeout status
- Error path: `jump` to a non-existent label — engine raises error, harness reports it

**Verification:**
- Harness boots within the Ren'Py process and enters the command loop
- Navigation commands cause labels to actually execute (store mutations are observable)
- Yield-point hooks return control to IPC without breaking the interaction cycle

---

### Phase 2: Engine Capabilities

- [ ] **Unit 4: Label Navigation Commands**

**Goal:** Implement the `jump`, `call`, `advance`, and `advance_until` methods on `RenpyEngine` that send commands over IPC and return structured results.

**Requirements:** R2, R6, R9

**Dependencies:** Unit 2 (engine runner), Unit 3 (harness dispatches these commands)

**Files:**
- Modify: `src/pytest_renpy/engine/runner.py` (or create `src/pytest_renpy/engine/commands.py` if runner grows large)
- Test: `tests/test_engine.py` (extend with navigation tests)

**Approach:**
- `jump(label) -> NavigationResult`: sends `{"cmd": "jump", "label": label}`, returns result with `at_label`, `store_snapshot`
- `call(label) -> NavigationResult`: sends `{"cmd": "call", "label": label}`, returns result with `target`, `store_snapshot`
- `advance(ticks=1) -> AdvanceResult`: sends `{"cmd": "advance", "ticks": N}`, returns tick count
- `advance_until(label=None, condition=None, max_ticks=1000) -> AdvanceResult`: sends `{"cmd": "advance_until", ...}`. The `condition` parameter is a callable evaluated on the pytest side — the engine sends state snapshots on each yield point, and the client evaluates the condition locally. Returns `status` ("reached" or "timeout") and `ticks_elapsed`
- `NavigationResult` and `AdvanceResult` are dataclasses with descriptive fields
- All commands raise `EngineError` if the engine process has died
- All commands respect a configurable timeout (default 30s)
- `advance_until` with a `condition` callable: the engine advances one tick at a time, sending state back after each yield point. The client evaluates `condition(state)` and either sends "continue" or "stop". This keeps arbitrary Python conditions on the pytest side (system Python) without needing to serialize lambdas across the IPC boundary

**Patterns to follow:**
- Layer 1's exception types (`JumpException`, `CallException`) for consistent API
- pytest-django's client API style for method naming

**Test scenarios:**
- Happy path: `jump("fenton_initialize")` returns `NavigationResult` with `at_label` showing where execution yielded
- Happy path: `call("init_utils")` returns `NavigationResult` with call target
- Happy path: `advance(ticks=5)` advances 5 ticks and returns tick count
- Happy path: `advance_until(label="fenton_intro_new_user")` advances until the label is reached, returns ticks_elapsed
- Happy path: `advance_until(condition=lambda s: s.get("input_mode", {}).get("active"))` advances until the condition is true
- Edge case: `advance_until` with `max_ticks=10` when the label is never reached — returns `status="timeout"` after 10 ticks
- Error path: `jump("nonexistent_label")` — returns an error response indicating the label was not found
- Error path: engine dies during `advance` — raises `EngineError` with stderr

**Verification:**
- Navigation commands work against a real Ren'Py project (terminalgame)
- `advance_until` correctly detects label arrival and condition satisfaction
- Timeout behavior works as expected with `max_ticks`

---

- [ ] **Unit 5: State Inspection Commands**

**Goal:** Implement `get_store`, `get_terminal_log`, and `get_available_commands` methods for reading engine state from tests.

**Requirements:** R5, R10

**Dependencies:** Unit 3 (harness handles `get_store` and `get_log` commands), Unit 4 (navigation commands to reach interesting states)

**Files:**
- Modify: `src/pytest_renpy/engine/runner.py`
- Test: `tests/test_engine.py` (extend)

**Approach:**
- `get_store(*vars) -> dict`: sends `{"cmd": "get_store", "vars": [...]}`, returns `{"var_name": value, ...}`. Values are deserialized from JSON; non-serializable objects arrive as `{"_type": "...", "_repr": "..."}` dicts
- `get_terminal_log() -> list[str]`: convenience wrapper around `get_store("terminal_log")`, returns the log list directly
- `get_available_commands() -> dict`: convenience wrapper around `get_store("cmd_dict")`, returns the command dict
- These are convenience methods — `get_store` is the general-purpose primitive, the others are helpers for common patterns in the reference games. Projects without `terminal_log` or `cmd_dict` simply get `None`
- Return types are plain Python dicts/lists (JSON-deserialized), not custom objects

**Patterns to follow:**
- Layer 1's `renpy_game.store` attribute-access pattern for API consistency
- Keep the API minimal — `get_store` is general, convenience helpers are thin wrappers

**Test scenarios:**
- Happy path: `get_store("typing_message")` returns the current value of `typing_message` from the engine
- Happy path: `get_store("terminal_log", "cmd_dict")` returns both values in a single round-trip
- Happy path: `get_terminal_log()` returns a list of strings after `game_print` has been called
- Happy path: `get_available_commands()` returns the command dict structure
- Edge case: `get_store("nonexistent_var")` returns `None` for that key (not an error)
- Edge case: `get_store` for a variable containing a Ren'Py `Character` object — returns `{"_type": "ADVCharacter", "_repr": "..."}`
- Edge case: `get_store` for a deeply nested dict with mixed serializable/non-serializable values

**Verification:**
- Can read terminalgame's `terminal_log`, `cmd_dict`, `typing_message`, `input_mode` after navigating to interesting states
- Non-serializable objects don't crash the pipeline

---

- [ ] **Unit 6: Menu Interaction and Game-Specific Input Adapters**

**Goal:** Implement `select_menu(index_or_text)` for interacting with `renpy.display_menu()` choices (generic, works with any Ren'Py project), and provide a hook for game-specific text input adapters.

**Requirements:** R4 (generic menu interaction), R3 (game-specific input via adapter hook)

**Dependencies:** Unit 4 (navigation to reach menu states), Unit 5 (state inspection to verify results)

**Files:**
- Modify: `src/pytest_renpy/engine/runner.py`
- Modify: `src/pytest_renpy/_test_harness.rpy` (menu interception logic)
- Test: `tests/test_engine.py` (extend)

**Approach:**

**Menu interaction (generic — works with any Ren'Py project):**
- The harness monkey-patches `renpy.display_menu()` at init time. When the engine calls `display_menu(options)`, instead of displaying a UI menu, the patched function:
  1. Sends `{"status": "menu_waiting", "options": [...]}` over IPC
  2. Blocks waiting for a `menu_select` command
  3. Returns the selected option's value to the engine
- `get_menu_options() -> list[tuple]`: returns the current menu's options (if the engine is in a menu-waiting state)
- `select_menu(choice) -> MenuResult`: sends `{"cmd": "menu_select", "index": N}` or `{"cmd": "menu_select", "text": "..."}`. The harness resolves text matches to the correct index. Returns `MenuResult` with `choice` and `jumped_to`
- If the test sends a navigation command and the engine hits a menu, the response includes `status: "menu_waiting"` so the test knows to call `select_menu()` or `get_menu_options()`

**Text input (game-specific adapter hook):**
- Ren'Py has no single programmatic text-input API. Games implement custom input handling — terminalgame uses `typing_message` + `game_send()`, others may use `renpy.input()` or custom screens. A generic `send_input(text)` that claims to work with any project would be misleading
- Instead, provide `set_store(**kwargs)` as a generic store-mutation command (sends `{"cmd": "set_store", "vars": {...}}`). Tests for terminalgame can use `set_store(typing_message="start")` followed by a call or jump to `game_send`. This is honest about what's game-specific vs generic
- Document the adapter pattern in README: "For games with custom input handling, use `set_store()` to set the input variable and navigation commands to trigger the handler"
- `renpy.input()` interception (if used by a project): similar to menu — monkey-patch to send prompt over IPC, block for response. This is a known Ren'Py API and can be intercepted generically. Deferred to post-v1 unless the spike reveals it's easy

**Patterns to follow:**
- kid-and-king's `renpy.display_menu()` pattern: options are `[(text, value), ...]` tuples

**Test scenarios:**
- Happy path: `select_menu(0)` selects the first menu option and returns the choice and jump target
- Happy path: `select_menu(text="Joe")` selects the menu option matching "Joe"
- Happy path: `get_menu_options()` returns the list of available options when the engine is at a menu
- Happy path: `set_store(typing_message="start")` mutates the store variable in the engine
- Edge case: `select_menu(index=99)` with only 3 options — returns error indicating invalid index
- Error path: `select_menu` when the engine is not at a menu — returns error status
- Integration: navigate to kid-and-king's `choose_a_reader` label, verify menu options include reader names, select one, verify jump target
- Integration: terminalgame input — `set_store(typing_message="start")` then navigate to trigger `game_send`, verify command is processed

**Verification:**
- Menu interaction works with kid-and-king's `renpy.display_menu()` pattern
- Menu interception doesn't break normal engine flow
- `set_store` provides a viable adapter path for game-specific input patterns

---

- [ ] **Unit 7: Test Isolation via Fresh Process (v1) and Optional Session Reuse (Stretch)**

**Goal:** Ensure perfect test isolation by default via fresh-process-per-test. If the spike (Unit 0) proves in-process reset is feasible, add session-scoped reuse as an opt-in optimization.

**Requirements:** R7, R12

**Dependencies:** Unit 0 (spike determines reset feasibility), Unit 4-6 (navigation, state inspection, and menu to create state worth isolating)

**Files:**
- Modify: `src/pytest_renpy/engine/runner.py`
- Modify: `src/pytest_renpy/_test_harness.rpy` (reset handler, if spike proves feasible)
- Test: `tests/test_integration_fixtures.py`

**Approach:**

**v1 default: fresh process per test**
- Each test gets a new engine process. The fixture calls `engine.start()` in setup and `engine.stop()` in teardown
- Perfect isolation — no state leakage possible
- Boot time target: < 5 seconds per test. If this is too slow for large test suites, optimize boot (e.g., pre-compiled .rpyc files, warm SDK cache) before attempting in-process reset
- `seed_random(n)` method sets the RNG seed at boot time via environment variable

**Stretch goal: session-scoped reuse (only if spike proves viable)**
- If Unit 0 demonstrates that store state can be reliably restored inside a running Ren'Py process, add `@pytest.mark.renpy(reuse_engine=True)` marker
- Session-scoped engine boots once, `reset()` between tests re-initializes store, clears persistent, reseeds random
- Known limitations to document if reuse is implemented:
  - Imported `.py` module state persists (Python module cache is process-wide)
  - Functions defined in `label python:` blocks are lost on reset (must re-navigate to define them)
  - Call stack and interaction state may not fully clear
- If the spike shows reset is not feasible, this stretch goal is dropped — no loss, fresh-process isolation is the correct default

**Patterns to follow:**
- pytest-django's `--reuse-db` pattern: expensive resource reuse is opt-in, not default
- Layer 1's per-test re-exec strategy (each test starts clean)

**Test scenarios:**
- Happy path: two sequential tests that both modify store state — second test sees clean state (fresh process)
- Happy path: test modifies `terminal_log`, next test sees empty `terminal_log`
- Happy path: `seed_random(42)` produces a deterministic sequence
- Edge case: engine crashes during one test — next test gets a new engine, no impact
- Integration: run 10 tests in sequence, verify no state leakage between any of them
- (If stretch goal implemented) Happy path: `reuse_engine=True` tests share a session-scoped engine and reset between tests
- (If stretch goal implemented) Happy path: reset completes in under 100ms

**Verification:**
- Tests are fully isolated by default (no leakage)
- Boot time is acceptable for typical test suites (< 5s per test, measured against reference games)
- Tests can run independently in any order

---

### Phase 3: Integration and Polish

- [ ] **Unit 8: Pytest Fixtures and Plugin Integration**

**Goal:** Wire Layer 2 into the pytest plugin with `renpy_engine` and `renpy_session` fixtures, CLI options, markers, and coexistence with Layer 1 fixtures.

**Requirements:** R8, R11

**Dependencies:** Unit 7 (fresh-process lifecycle per test)

**Files:**
- Modify: `src/pytest_renpy/plugin.py` (add `--renpy-sdk` option, `@pytest.mark.renpy_flow` marker)
- Modify: `src/pytest_renpy/fixtures.py` (add `renpy_engine`, `renpy_session`)
- Test: `tests/test_integration_fixtures.py`

**Approach:**

**New CLI option:**
- `--renpy-sdk <path>`: path to the Ren'Py SDK directory (required for Layer 2 tests, not needed for Layer 1)

**New marker:**
- `@pytest.mark.renpy_flow`: marks tests as Layer 2 integration tests. Tests with this marker require `--renpy-sdk` to be set. Tests without the marker continue to work with Layer 1 fixtures only

**New fixtures:**
- `renpy_engine` (function scope, v1): boots a fresh `RenpyEngine` per test, yields it, stops on teardown. Skips if `--renpy-sdk` is not provided. If session-scoped reuse is proven viable (Unit 0 spike), a session-scoped variant is added behind `@pytest.mark.renpy(reuse_engine=True)`
- `renpy_session` (function scope): convenience alias for `renpy_engine` that is the primary fixture test authors use. Abstracts whether the engine is fresh or reused

**Coexistence with Layer 1:**
- Layer 1 fixtures (`renpy_game`, `renpy_store`, `renpy_mock`) continue to work unchanged
- Layer 2 fixtures (`renpy_engine`, `renpy_session`) are independent — a test file can use either or both
- Both layers share `--renpy-project` for the project path
- Layer 2 fixtures are **always registered** (fixtures register at import time, not conditionally). When `--renpy-sdk` is absent, the fixtures call `pytest.skip()` on first use. This is the standard pytest pattern — Layer 1-only users see no difference unless they request a Layer 2 fixture

**Error handling:**
- If `--renpy-sdk` is not set and a test requests `renpy_engine`/`renpy_session`: `pytest.skip("--renpy-sdk required for integration tests")`
- If the SDK path is invalid: `pytest.exit("Ren'Py SDK not found at ...")`
- If the engine fails to boot: `pytest.exit("Engine failed to start: ...")`

**Patterns to follow:**
- pytest-django's `django_db` marker for conditional fixture behavior
- Layer 1's existing plugin structure in `plugin.py`

**Test scenarios:**
- Happy path: `renpy_session` fixture provides a freshly booted engine per test
- Happy path: `renpy_engine` fixture boots a fresh engine per test (v1 default); session-scoped reuse is stretch-only
- Happy path: Layer 1 and Layer 2 tests coexist in the same pytest invocation
- Happy path: `--renpy-sdk` option appears in `pytest --help`
- Edge case: test requests `renpy_session` without `--renpy-sdk` — test is skipped with clear message
- Edge case: Layer 1 tests run without `--renpy-sdk` — no change in behavior
- Error path: invalid `--renpy-sdk` path — pytest exits with clear error message

**Verification:**
- `pytest --help` shows both `--renpy-project` and `--renpy-sdk` options
- Layer 1 tests pass without `--renpy-sdk`
- Layer 2 tests run and pass with valid `--renpy-sdk`
- Both layers run together in a single `pytest` invocation

---

- [ ] **Unit 9: Proof-of-Concept Integration Tests**

**Goal:** Write real integration tests against the three reference games that demonstrate Layer 2's value — testing label flow, input simulation, menu interaction, and label-scoped functions.

**Requirements:** R1-R12 (end-to-end validation)

**Dependencies:** Unit 8 (fixtures complete)

**Files:**
- Create: `examples/terminalgame/test_flow.py`
- Create: `examples/kid-and-king/test_flow.py`
- Create: `examples/minimum-viable-rpg/test_flow.py`
- Modify: `examples/terminalgame/conftest.py` (add SDK path config)
- Modify: `examples/kid-and-king/conftest.py`
- Modify: `examples/minimum-viable-rpg/conftest.py`

**Approach:**
- Each test file demonstrates a different Layer 2 capability against a real game
- Tests serve as both validation and living documentation of the API

**Test scenarios:**

**terminalgame (`test_flow.py`) — label flow and store mutation:**
- Happy path: jump to `fenton_initialize`, advance until `fenton_intro_new_user`, verify "no previous session found" in terminal_log
- Happy path: jump to `fenton_intro_start`, advance until `input_mode["active"]`, verify `cmd_dict["base_cmds"]["save"]["usable"]` is False and `cmd_dict["base_cmds"]["quit"]["usable"]` is True
- Happy path: use `set_store(typing_message="start")` + navigate to trigger `game_send`, verify command dispatch works (adapter pattern for game-specific input)
- Integration: full narrative sequence — boot → Fenton intro → verify store mutations across label transitions

**kid-and-king (`test_flow.py`) — menu interaction:**
- Happy path: navigate to `choose_a_reader`, get menu options, verify reader names appear
- Happy path: select menu option "Joe", verify jump to `talk_to_joe` (or equivalent)
- Happy path: after talking to Joe, reader state `readers["Joe"].talked_to` is True

**minimum-viable-rpg (`test_flow.py`) — label python: block functions:**
- Happy path: after engine boot and init chain execution, functions from `label init_utils:` are available (e.g., `get_location_by_name` is callable via store)
- Happy path: defaults from `label start:` are set (variables that Layer 1 couldn't reach)
- Happy path: navigate to `visit_location`, verify menu options include location-specific actions

**Verification:**
- All tests pass against real Ren'Py projects with a valid SDK
- Each test completes navigation/commands in under 500ms (excluding engine boot)
- Tests demonstrate capabilities that are impossible with Layer 1 alone

---

- [ ] **Unit 10: Documentation Update**

**Goal:** Update README and package metadata to document Layer 2 capabilities, configuration, and usage.

**Requirements:** R8, R11

**Dependencies:** Unit 9 (proof-of-concept validates everything works)

**Files:**
- Modify: `README.md` (add Layer 2 section: installation, SDK setup, fixture API, example tests)
- Modify: `pyproject.toml` (update description, add optional dependency group for Layer 2)

**Approach:**
- README adds a "Integration Testing (Layer 2)" section covering:
  - Prerequisites (Ren'Py SDK download)
  - Configuration (`--renpy-sdk` option)
  - Fixture API (`renpy_session.jump()`, `.advance_until()`, `.get_store()`, `.set_store()`, `.select_menu()`, etc.)
  - Example tests (from Unit 9)
  - Troubleshooting: SDL driver issues, SDK path resolution, timeout handling
- `pyproject.toml` updates description to mention integration testing

**Test expectation: none** — this unit is documentation and metadata, no behavioral changes.

**Verification:**
- A new user can follow the README to set up Layer 2 and run integration tests
- README accurately reflects the implemented API

## System-Wide Impact

- **Interaction graph:** Layer 2 introduces a subprocess managed by the pytest process. The engine operates on a **temp copy** of the project's game directory (not the original) — the harness .rpy file is placed in the copy, and the original project tree is never modified. The IPC socket and save data use temp directories. All temp resources are cleaned up on teardown (with atexit fallback for crash safety).
- **Error propagation:** Engine crashes propagate as `EngineError` with stderr output. IPC timeouts propagate as `TimeoutError`. Invalid commands propagate as structured error responses. All errors include enough context for diagnosis.
- **State lifecycle risks:** In v1, each test gets a fresh engine process — no state leakage is possible. If session-scoped reuse is added as a stretch goal, the main risk is incomplete state reset (imported `.py` module state persists across resets due to Python's module cache). The stretch-goal reuse mode would be opt-in, so the default remains safe.
- **API surface parity:** Layer 2 fixtures (`renpy_engine`, `renpy_session`) are a distinct API from Layer 1 fixtures (`renpy_game`, `renpy_store`, `renpy_mock`). Both coexist in the same plugin. Exception types are shared.
- **Integration coverage:** Unit 9 provides end-to-end coverage against three real Ren'Py projects of varying complexity.
- **Unchanged invariants:** Layer 1 fixtures, parser, mock, and loader are not modified (except plugin.py gains the `--renpy-sdk` option). Existing Layer 1 tests continue to pass unchanged. Layer 2 fixtures are always registered but `pytest.skip()` when `--renpy-sdk` is absent.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| **Control-flow mechanism may not work as assumed** | This is the highest risk. The spike (Unit 0) is a mandatory gate that must validate the trampoline/yield-point approach before any other unit begins. If the spike fails, the plan pivots to an alternative architecture |
| Ren'Py's event loop resists external control | Harness runs *inside* the event loop as a normal label. Navigation exceptions propagate to Ren'Py normally (not caught by the harness). Control returns to IPC via yield-point hooks. Validated by the spike before full implementation |
| `advance()` bypasses the interaction cycle | The spike must validate that the chosen mechanism actually processes Ren'Py interactions (not just a no-op loop). `renpy.pause(0)` semantics and interaction-cycle driving are tested in the spike |
| Recursive tick loop (`handle_tick` calling itself) exhausts call stack during `advance` | `max_ticks` parameter provides a safety valve. Implementation may need to detect and break recursion or limit tick-based advancement. Stack depth is monitored in tests |
| `renpy.display_menu()` monkey-patch breaks under certain Ren'Py versions | The patch is applied at `init -999` (earliest possible) and intercepts at the Python level. If Ren'Py's menu implementation changes, the patch may need updating. Tested against Ren'Py 8.x |
| Cross-Python serialization fails for complex store objects | Graceful fallback serialization (`{"_type": "...", "_repr": "..."}`) ensures the IPC pipeline never crashes. Tests inspect primitives and simple structures; complex objects are inspectable via repr |
| Engine boot time exceeds 5-second target | v1 uses fresh process per test. If boot time makes this impractical, optimize boot (pre-compiled .rpyc, warm cache) before attempting session-scoped reuse |
| Harness injection mutates the game tree | Engine operates on a **temp copy** of the project's game directory. The original project tree is never modified. Temp copy is cleaned up on stop, with atexit fallback for crash safety |
| Harness .rpy file conflicts with game's own splashscreen label | Harness uses `label splashscreen:` override at `init -999` priority. If a game defines its own splashscreen, the harness takes precedence. This is intentional — the harness needs to intercept before any game code runs |
| Parallel test sessions on the same machine | Socket path includes a unique temp directory per session. No port conflicts possible with Unix domain sockets |
| SDK Python path varies by platform | Engine runner discovers the Python binary by searching known SDK subdirectory patterns (`lib/py3-linux-x86_64/python`, `lib/py3-mac-*`, etc.). Clear error message if not found |
| Generic `send_input` doesn't exist in Ren'Py | v1 limits generic input to menu selection (`renpy.display_menu`). Game-specific input (terminalgame's `typing_message`) uses `set_store()` + navigation as an adapter pattern. `renpy.input()` interception deferred to post-v1 |

## Sources & References

- **Origin document:** [docs/plans/layer2-label-flow-integration.md](docs/plans/layer2-label-flow-integration.md)
- **Layer 1 plan:** [docs/plans/2026-05-06-001-feat-layer1-mock-unit-testing-plan.md](docs/plans/2026-05-06-001-feat-layer1-mock-unit-testing-plan.md)
- **Bug catalog:** [docs/discovered-bugs.md](docs/discovered-bugs.md)
- **Target game (extreme test case):** terminalgame at `/projects/xander/terminalgame/` — recursive tick loop, command dispatch, input gating
- **Reference game (visual novel):** the-kid-and-the-king-of-chicago at `/projects/masked_fox/the-kid-and-the-king-of-chicago/` — `renpy.display_menu()` patterns, Reader objects
- **Reference game (RPG):** minimum-viable-rpg-renpy at `/projects/masked_fox/minimum-viable-rpg-renpy/` — label `python:` block functions, defaults inside labels, dynamic menu construction
- External: Ren'Py Python statement reference, Unix domain socket programming

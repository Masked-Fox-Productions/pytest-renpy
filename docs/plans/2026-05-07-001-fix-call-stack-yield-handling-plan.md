---
title: "fix: Call Stack Depth Tracking and Mid-Label Yield Auto-Advance"
type: fix
status: active
date: 2026-05-07
origin: docs/investigations/2026-05-07-renpy-call-and-mid-label-yields.md
---

# fix: Call Stack Depth Tracking and Mid-Label Yield Auto-Advance

## Overview

The test harness yields control to the test at every `renpy.ui.interact` call, including intermediate say statements (`NA(...)`) inside called labels. This means tests see stale state — code after the yield hasn't run yet. This plan adds call-stack-depth tracking so the harness auto-advances through intermediate yields when inside a `call` frame, and fixes two related issues: `exec_code` not handling `CallException` properly, and missing `start` label fallback for games that don't define one.

## Problem Frame

When a test calls `engine.call("some_label")` or `engine.exec_code("attack_with('hatchet', 'bekri')")` (where `attack_with` internally calls `renpy.call()`), the target label executes but pauses at every inline say statement (`NA(...)`) that triggers `renpy.ui.interact`. The test regains control at these intermediate yield points and sees state before the label has finished its work.

In real Ren'Py, `call some_label` executes the label through all its interactions (the player clicks through dialogue) and returns to the caller when done. The caller never sees intermediate yields. The harness needs to mirror this behavior.

Three concrete problems:

1. **No auto-advance for call frames.** Every yield goes to IPC regardless of whether we're inside a `call` frame or at a top-level yield point. 16 tests fail because of this.

2. **`exec_code` + `CallException` leaves the protocol in an inconsistent state.** When `exec_code("attack_with('hatchet', 'bekri')")` triggers `renpy.call()` inside the game code, the `CallException` is re-raised without sending a response. The next message the runner receives is a `yielded` from an intermediate yield point, not a completion signal.

3. **Missing `start` label crashes.** After a jumped-to label returns, execution falls through to Ren'Py's startup flow which calls `renpy.jump("start")`. Games without a `start` label (like Forest's Bane, which uses `start_run`) crash.

(see origin: `docs/investigations/2026-05-07-renpy-call-and-mid-label-yields.md`)

## Requirements Trace

- R1. When `engine.call()` or `engine.exec_code()` triggers a `CallException`, the harness auto-advances through known-safe intermediate yields until the called label returns, then yields to IPC with a completion response
- R2. `engine.jump()` behavior is unchanged — every yield point still pauses and yields to IPC (jump has no "return" concept)
- R3. `exec_code` that triggers `CallException` sends a coherent response to the runner when the called label completes (not a raw `yielded` from an intermediate point)
- R4. Games without a `start` label do not crash when a jumped-to label returns
- R5. Auto-advance does not break menu interaction — if a called label presents a menu (`renpy.display_menu()`), the auto-advance pauses and yields the menu to the test
- R6. Auto-advance does not break `engine.advance()` / `engine.advance_until()` — these must still yield at every interaction point
- R7. Auto-advance only skips known-safe interaction types (say/pause). Unknown or branching interaction types (input, screen interactions, imagemaps) yield to IPC even during auto-advance

## Scope Boundaries

- IPC wire framing is unchanged (JSON lines over Unix socket), but the **response status vocabulary is extended** — `completed` is added as a new status value, and all receiver paths in the runner must handle it
- No changes to `engine.jump()` behavior (yields at every interaction)
- No changes to `engine.advance()` / `engine.advance_until()` semantics
- `attribute_check` test fixes are game-specific to Forest's Bane and out of scope
- The `reached_target` sentinel inconsistency (small vs. medium/large Bekri) is a game-level issue, not a harness issue

## Context & Research

### Relevant Code and Patterns

- `src/pytest_renpy/engine/_test_harness.rpy` — the engine-side harness. Key functions: `_harness_command_loop()` (line 88), `_patched_ui_interact()` (line 156), `_patched_display_menu()` (line 176), `label _harness_idle` (line 249)
- `src/pytest_renpy/engine/runner.py` — the pytest-side engine client. Key methods: `call()` (line 175), `exec_code()` (line 295), `_recv_navigation()` (line 246)
- `examples/forests-bane/test_bekri_flow.py` — demonstrates the yield problem via `run_monster_movement()` (line 62) which manually polls `advance(1)` in a loop checking `reached_target`
- `spike/fixture_game/game/script.rpy` — minimal fixture game with labels, store vars, pause, and menu. Used for existing harness tests in `tests/test_engine.py`

### Institutional Learnings

- `CallException` requires `from_current=True` in Ren'Py 8.3.7 so the return site is the current node (the command loop), not the unset `next_node`
- The `_harness_idle` recursive self-call pattern grows the Ren'Py call stack unboundedly — not directly addressed in this plan but worth noting as future tech debt
- `_patched_ui_interact` always returns `True` unconditionally — any game code that depends on the interaction return value gets wrong data. Not addressed here but related
- Ren'Py passes `type=` keyword to `ui.interact` indicating the interaction kind (e.g., `"say"`, `"menu"`, `"input"`, `"pause"`). The harness already reads this via `kwargs.get("type", "unknown")` at line 160

## Key Technical Decisions

- **Stack-depth tracking via `renpy.game.context().call_stack`:** When the harness processes a `call` command or `exec_code` triggers a `CallException`, it records the current call stack depth. In `_patched_ui_interact`, if the current depth exceeds the recorded baseline, the interaction is a candidate for auto-advance. This mirrors Option C from the investigation and is the most natural mapping to real Ren'Py behavior. **Important:** the completion response is NOT sent from `_patched_ui_interact` — it is sent from `_harness_idle` on re-entry (see below). The `_patched_ui_interact` depth check only governs skip-vs-yield; the completion signal path goes through `_harness_idle`.

- **Auto-advance only known-safe interaction types:** Not every `ui.interact` call is safe to skip. Ren'Py dispatches many interaction types through `ui.interact`: say dialogues, pauses, input prompts, screen interactions, imagemaps, and custom screens. Auto-advancing an input prompt or screen interaction by returning `True` can silently corrupt game state. The harness must maintain an allowlist of safe-to-skip interaction types (initially: `"say"`, `"pause"`, and `"with"` transitions). Interactions with unknown or branching types yield to IPC even during auto-advance, giving the test the opportunity to handle them. The allowlist is defined as a set in the harness and can be extended as more types are proven safe.

- **JumpException inside a called label clears auto-advance:** If code inside a called label raises `JumpException` (e.g., `renpy.jump("somewhere")`), the call frame is popped and execution transfers to the jump target. At the next yield point in the jump target, `_patched_ui_interact` sees depth <= baseline and clears auto-advance state. Since `_harness_idle` is not re-entered (the jump bypassed the return path), `_patched_ui_interact` itself sends a `yielded` response (not `completed`) and enters the command loop. The test receives a normal `yielded` at whatever label the jump landed on. This is the correct behavior: a jump inside a call is an abnormal exit, and the test should handle the unexpected label.

- **Auto-advance pauses at menus:** `_patched_display_menu` always yields to IPC regardless of auto-advance state. After the test calls `select_menu()`, auto-advance state remains active (if depth is still above baseline), so the harness continues auto-advancing after the menu selection until the call completes.

- **Command classification during auto-advance pause:** When auto-advance is active but the harness has yielded to IPC (unknown interaction type, menu, or safety-limit hit), the command received from `_harness_command_loop()` determines whether auto-advance continues or is cancelled:
  - **Preserve auto-advance** (resume after command): `continue`, `menu_select` — these advance execution within the current call frame; auto-advance state remains active and resumes at the next `_patched_ui_interact` call
  - **Cancel auto-advance** (clear all state before raising): `jump`, `call`, `stop`, `exec` (when it raises navigation) — these abandon the current call frame. Before raising the exception, the command handler must clear all auto-advance state (`_harness_auto_advance_depth = None`, `_harness_pending_call_response = False`, counter = 0). This prevents stale auto-advance state from leaking into the new navigation context. `call` also sets fresh auto-advance state for the new call after clearing
  - **Neutral** (no effect on auto-advance): `ping`, `get_store`, `set_store`, `eval`, `exec` (when it does NOT raise navigation) — these are non-navigating commands handled inline; auto-advance state is untouched

- **Runner-side menu-during-call protocol:** When `engine.call()` receives a `menu_waiting` response mid-auto-advance, it returns a `NavigationResult` with `yield_type="menu_waiting"` to the test. The test calls `select_menu()`, which sends the selection and receives the next response. If auto-advance is still active, the harness auto-advances through more yields after the menu. `select_menu()` must loop receiving responses until it gets a terminal response: `completed` (call finished after menu), `menu_waiting` (another menu), or `yielded` (call was interrupted by a jump or unknown interaction type). It cannot return immediately after the selection because the harness may auto-advance silently after the menu.

- **Explicit protocol status vocabulary:** The harness-to-runner response `status` field has a defined vocabulary. All receiver paths in the runner (`_recv_navigation`, `recv`, `exec_code`, `send_command`) must handle every status:
  - `pong` — response to `ping`
  - `ready` — engine boot complete
  - `ok` — command succeeded (get_store, set_store, exec without navigation)
  - `yielded` — execution paused at an interaction point (includes `at_label`, `yield_type`)
  - `menu_waiting` — execution paused at a menu (includes `options`, `at_label`)
  - `completed` — **new** — a called label returned normally after auto-advance (includes `at_label`, `yield_type: "completed"`)
  - `error` — command failed (includes `message`)
  - `stopping` — engine shutting down

- **`_harness_idle` sends completion response on re-entry after auto-advance:** When a called label returns and execution re-enters `_harness_idle`, the harness checks `_harness_pending_call_response`. If true, it clears **all** auto-advance state (`_harness_auto_advance_depth = None`, `_harness_pending_call_response = False`, counter = 0), then sends `{"status": "completed", "at_label": ..., "yield_type": "completed"}` before entering the command loop. This is the only path for normal call completion — `_patched_ui_interact` does not send completion responses. This gives `exec_code` and `call` a clean completion signal. The full state cleanup prevents any subsequent command from being misclassified as part of the prior call.

- **Fallback `start` label mechanism must be spike-proven:** The harness needs to catch fallthrough when a jumped-to label returns and the game has no `start` label. The specific mechanism (static `label start:`, dynamic registration, `config.label_overrides`) depends on Ren'Py's duplicate label behavior, which must be verified before implementation. This is gated behind a spike (Unit 1).

## Open Questions

### Resolved During Planning

- **Should auto-advance apply to `jump` too?** No. `jump` has no return concept — the test explicitly controls advancement after a jump. Auto-advance only applies to `call` semantics (including `exec_code`-triggered calls).

- **What happens if a called label hits a menu during auto-advance?** The menu always yields to IPC, even during auto-advance. This ensures the test can make menu selections inside called labels. After the test selects, auto-advance resumes if still inside the call frame.

- **Should auto-advance be opt-in or default for `call`?** Default. This matches real Ren'Py behavior where `call` executes the label to completion. Tests that need to inspect intermediate state inside a called label can use `jump` + manual `advance` instead.

- **What happens when a called label jumps instead of returning?** The jump pops the call stack, so at the next yield point `_patched_ui_interact` sees depth <= baseline. Auto-advance state is cleared, and a normal `yielded` response is sent (not `completed`). The test receives a yield at whatever label the jump landed on. This is correct — a jump inside a call is an abnormal exit. The `_harness_pending_call_response` flag is also cleared since the call didn't complete normally.

- **Should all `ui.interact` types be auto-advanced?** No. Only known-safe, non-branching types (`say`, `pause`, `with`) are auto-advanced. Unknown interaction types yield to IPC even during auto-advance. This prevents silently corrupting game state from input prompts, screen interactions, imagemaps, or custom screens that depend on the return value.

### Deferred to Implementation

- **Exact call stack depth comparison semantics:** Whether to compare `len(call_stack)` or use a more robust depth indicator. The spike (Unit 1) must log actual depth values at the raise point and at the first yield to determine the correct comparison.

- **Edge case: recursive calls inside called labels.** If a called label itself calls another label (nested `renpy.call()`), the stack depth increases further. Auto-advance should handle this naturally (depth stays above baseline until all nested calls return), but needs verification in the spike.

- **Safety counter threshold:** Unit 2 implements a max auto-advance counter, but the specific limit may need tuning based on real-world label complexity.

- **Interaction type allowlist expansion:** The initial allowlist (`say`, `pause`, `with`) may need to grow as more interaction types are proven safe. Each addition should be validated against actual Ren'Py behavior.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
Auto-advance state machine:

TWO completion paths exist — do not confuse them:

Path A: Normal return (called label returns)
  → _harness_idle re-enters → sends "completed" → enters command loop

Path B: Jump-from-call (called label jumps instead of returning)
  → jump target yields → _patched_ui_interact sees depth <= baseline
  → clears auto-advance → sends "yielded" (not "completed")
  → enters command loop from _patched_ui_interact

Decision tree inside _patched_ui_interact:

                    ┌──────────────────┐
                    │  _auto_depth is   │
                    │  None?            │
                    └────┬─────────┬───┘
                         │ yes     │ no
                         ▼         ▼
                 ┌──────────┐  ┌───────────────────┐
                 │ Normal:  │  │ current_depth >    │
                 │ yield to │  │ _auto_depth?       │
                 │ IPC      │  └───┬──────────┬────┘
                 └──────────┘      │ yes      │ no (jump-from-call)
                                   ▼          ▼
                         ┌──────────────┐  ┌──────────────────┐
                         │ type in      │  │ Clear auto state,│
                         │ safe set?    │  │ clear pending    │
                         └──┬──────┬───┘  │ flag, yield to   │
                            │ yes  │ no   │ IPC as "yielded" │
                            ▼      ▼      └──────────────────┘
                     ┌────────┐ ┌──────────┐
                     │ Auto:  │ │ Unknown  │
                     │ return │ │ type:    │
                     │ True   │ │ yield to │
                     │(no IPC)│ │ IPC with │
                     └────────┘ │yield_type│
                                └──────────┘

_patched_display_menu ALWAYS yields to IPC (never auto-advanced).
After menu selection, auto-advance resumes if depth still > baseline.
```

**Protocol flow for `call` with auto-advance (normal return):**

```
Test                          Harness                    Ren'Py
 │                              │                          │
 │ {"cmd":"call","label":"X"}   │                          │
 │─────────────────────────────>│                          │
 │                              │ record stack depth       │
 │                              │ raise CallException      │
 │                              │─────────────────────────>│
 │                              │                          │ enter label X
 │                              │                          │ ... executes ...
 │                              │   _patched_ui_interact   │ NA("text") type=say
 │                              │<─────────────────────────│
 │                              │ depth > base, say=safe   │
 │                              │ return True ────────────>│
 │                              │                          │ ... continues ...
 │                              │   _patched_ui_interact   │ NA("more") type=say
 │                              │<─────────────────────────│
 │                              │ depth > base, say=safe   │
 │                              │ return True ────────────>│
 │                              │                          │ return (label done)
 │                              │<─────────────────────────│
 │                              │ re-enter _harness_idle   │
 │  {"status":"completed",...}  │                          │
 │<─────────────────────────────│                          │
```

**Protocol flow for `call` with unknown interaction type mid-label:**

```
Test                          Harness                    Ren'Py
 │                              │                          │
 │ {"cmd":"call","label":"Y"}   │                          │
 │─────────────────────────────>│                          │
 │                              │ record stack depth       │
 │                              │ raise CallException ────>│
 │                              │                          │ enter label Y
 │                              │   _patched_ui_interact   │ type=input
 │                              │<─────────────────────────│
 │                              │ depth > base, but input  │
 │                              │ NOT in safe set → yield  │
 │  {"status":"yielded",        │                          │
 │   "yield_type":"input",...}  │                          │
 │<─────────────────────────────│                          │
 │                              │ (blocks for next cmd)    │
```

## Implementation Units

### Phase 0: Spike (gate for all subsequent units)

- [ ] **Unit 1: Spike — call-stack return path and duplicate label behavior**

**Goal:** Prove two assumptions before implementation begins: (a) the exact `_harness_idle` re-entry path after a `CallException` raised from `_harness_command_loop`, and (b) whether Ren'Py errors on duplicate label definitions.

**Requirements:** R1, R4

**Dependencies:** None

**Files:**
- Modify: `spike/fixture_game/game/script.rpy` (add labels for call/return, nested call, call-with-jump, call-with-menu, no-yield call, exec-triggered call)
- Create: `spike/call_stack_spike.py` (driver script that logs call_stack depth, current node, and label at key points)

**Approach:**

**Call-stack return path (blocks Units 2-5):**
- Add logging to `_harness_idle`, `_patched_ui_interact`, and the `call` command handler that prints `renpy.game.context().call_stack` depth and `renpy.game.context().current` node at each decision point
- Add fixture-game labels that exercise: (1) call + say + return, (2) call + nested call + return, (3) call + jump (no return), (4) call + menu + return, (5) call with no yields, (6) exec that triggers `renpy.call()`
- Run each scenario with the logging harness and record: what depth is at the raise point, what depth is at the first yield in the called label, what node executes immediately after the called label returns, whether `_harness_idle` re-enters as expected
- Document exact depth delta (is it +1? +2?) between baseline and the called label's yields

**Duplicate label behavior (blocks Unit 4):**
- Add `label start:` to the test harness while the fixture game already defines `label start:` in `script.rpy`
- Boot the engine and observe: does Ren'Py error, warn, or silently override? Which definition wins?
- If duplicate labels error, test alternatives: (a) define the label with a unique name and register it at init time via `renpy.game.script.namemap`, (b) use `config.after_load_callbacks`, (c) patch the label lookup

**Test scenarios:**
- Spike 1: `call` to label with 2 say statements — log depth at raise, depth at first yield, depth at second yield, node after return
- Spike 2: `call` to label that itself calls another label — log depth at each level
- Spike 3: `call` to label that jumps instead of returning — log depth at jump target's first yield
- Spike 4: `exec_code("renpy.call('some_label')")` — log depth at raise (inside exec handler), depth at first yield
- Spike 5: duplicate `label start:` in both harness and game — observe Ren'Py's behavior
- Spike 6: `call` to a label with no yields — does `_harness_idle` re-enter immediately?

**Verification:**
- A `spike/README.md` or inline comments document: exact depth values at each point, the re-entry node after call return, and the duplicate label behavior
- Findings determine whether Units 2-5 proceed as designed or need adjustment
- If `_harness_idle` does NOT re-enter as expected, the completion signal path must be redesigned before proceeding

**Exit criteria:**
- If depth at called label yields is consistently `baseline + N` (determine N) → Units 2-3 use that comparison
- If `_harness_idle` re-enters correctly → Unit 2-3 completion path is confirmed
- If `_harness_idle` does NOT re-enter → alternative completion signal mechanism needed (e.g., flag check in `_patched_ui_interact` for the first yield after depth returns to baseline)
- If duplicate labels work → Unit 4 uses static `label start:`
- If duplicate labels error → Unit 4 uses the alternative mechanism proven in the spike

---

### Phase 1: Protocol and core mechanism

- [ ] **Unit 2: Define protocol statuses and add auto-advance to harness**

**Goal:** Extend the harness with call-stack-depth tracking, interaction-type-aware auto-advance, and the `completed` status response. Update all runner receiver paths to handle the full status vocabulary.

**Requirements:** R1, R2, R5, R6, R7

**Dependencies:** Unit 1 (spike determines depth comparison semantics and completion path)

**Files:**
- Modify: `src/pytest_renpy/engine/_test_harness.rpy`
- Modify: `src/pytest_renpy/engine/runner.py`

**Approach:**

**Harness changes:**
- Define interaction type allowlist: `_SAFE_AUTO_ADVANCE_TYPES = {"say", "pause", "with"}`. Only these types are auto-advanced. All others yield to IPC even during auto-advance
- Add global state: `_harness_auto_advance_depth` (None when not in auto-advance mode, integer baseline when tracking a call frame), `_harness_pending_call_response` (boolean), `_harness_auto_advance_count` (integer counter for safety limit)
- In the `call` command handler: record call stack depth (using the exact comparison from the spike), set `_harness_pending_call_response = True`, reset counter to 0, then raise `CallException`
- In `_patched_ui_interact`:
  - If `_harness_auto_advance_depth is None` → normal yield to IPC (existing behavior)
  - If depth > baseline AND `interact_type` in `_SAFE_AUTO_ADVANCE_TYPES` AND counter < limit → increment counter, return True (no IPC)
  - If depth > baseline AND `interact_type` NOT in safe set → yield to IPC with the actual `yield_type` (test must handle the unknown interaction)
  - If depth > baseline AND counter >= limit → clear all auto-advance state, yield to IPC with `yield_type` including a `"auto_advance_limit": true` field as a warning
  - If depth <= baseline → this is the jump-from-call path: clear all auto-advance state (`_harness_auto_advance_depth = None`, `_harness_pending_call_response = False`, counter = 0), yield to IPC as normal `yielded`
- In `_harness_idle` label: before calling `_harness_command_loop()`, check `_harness_pending_call_response`. If true, clear **all** auto-advance state (`_harness_auto_advance_depth = None`, `_harness_pending_call_response = False`, counter = 0), send `{"status": "completed", "at_label": ..., "yield_type": "completed"}`, then enter command loop. This mirrors the safety-limit cleanup path — both terminal paths must leave identical clean state
- `_patched_display_menu` core behavior is unchanged — menus always yield to IPC regardless of auto-advance state. However, the menu handler must account for non-`menu_select` commands received while a menu is pending during a call. After `_harness_command_loop()` returns, the menu handler currently only processes `menu_select`. If the test sends `jump`, `call`, `stop`, or a navigation-triggering `exec` while a menu is pending, `_harness_command_loop()` raises the appropriate exception directly (before returning to the menu handler), so the menu is abandoned via exception propagation — no menu handler changes needed. The command classification above (Finding 2) ensures auto-advance state is cleared before these exceptions propagate. Non-navigating commands (`ping`, `get_store`, `set_store`, `eval`, non-navigating `exec`) are handled inline by `_harness_command_loop()` and loop back for the next command, so the menu handler never sees them. The only command that returns to the menu handler is `menu_select`

**Safety counter semantics:** When the counter exceeds the limit, it is a terminal interruption of auto-advance. All auto-advance state is cleared (`_harness_auto_advance_depth = None`, `_harness_pending_call_response = False`, counter = 0). The harness yields to IPC as a normal `yielded` with the additional `auto_advance_limit: true` field. The test can then decide whether to manually advance or abort. The harness does NOT remain in auto-advance mode — it is fully reset.

**Runner changes:**
- Audit every receive path: `_recv_navigation()`, `recv()`, `exec_code()`, `send_command()`, `advance()`, `advance_until()`
- `_recv_navigation()`: handle `completed` (return as-is — response includes `yield_type: "completed"`), `yielded` (return as-is), `menu_waiting` (set pending menu, return), `error` (raise EngineError). The `completed` response carries `yield_type: "completed"` from the harness, so `NavigationResult(yield_type=resp.get("yield_type", ""))` works correctly without runner-side mapping
- `recv()`: handle `completed` in addition to existing statuses
- `exec_code()`: handle `completed` status (exec triggered a call that finished)
- `call()` return type: `NavigationResult` with `yield_type` reflecting the actual status (`"completed"`, `"yielded"`, `"menu_waiting"`)
- **Command-specific helpers must validate expected statuses:** `get_store()`, `set_store()`, and `eval_expr()` use `send_command()` and assume an `ok` payload. If they receive an unexpected navigation status (`yielded`, `completed`, `menu_waiting`), this indicates a protocol desync — the harness sent a navigation response when the runner expected a data response. These helpers must raise `EngineError` on any status other than `ok` or `error` (which is already handled). This prevents silent data corruption where a navigation response is misinterpreted as a data response

**Patterns to follow:**
- Existing `_patched_ui_interact` pattern for IPC yield
- Existing `_harness_command_loop` pattern for exception-based navigation

**Test scenarios:**
- Happy path: `call` to a label with 3 say statements — harness auto-advances past all 3, test receives single `completed` response with final state
- Happy path: `call` to a label that modifies store then has say statements — test sees final store values, not intermediate
- Happy path: `call` to a label with a menu inside — auto-advance pauses at menu, test receives `menu_waiting`, selects, auto-advance resumes
- Happy path: `jump` to a label with say statements — still yields at every point (no auto-advance)
- Happy path: `advance()` after a jump — still advances one tick at a time
- Edge case: `call` to a label that calls another label (nested call) — auto-advance continues through both, returns when outer call completes
- Edge case: `call` to a label that has no yield points — completes immediately, test receives `completed`
- Edge case: `call` to a label that internally jumps — auto-advance clears, test receives `yielded` at the jump target
- Edge case: `call` to a label with an unknown interaction type (e.g., `renpy.input()`) — auto-advance pauses, test receives `yielded` with `yield_type="input"`
- Edge case: safety counter exceeded — auto-advance state fully cleared, test receives `yielded` with `auto_advance_limit: true`
- Error path: `call` to a nonexistent label — engine error propagated normally
- Error path: `get_store()` / `set_store()` / `eval_expr()` receiving an unexpected navigation status (protocol desync) — raises `EngineError`

**Verification:**
- `engine.call("label_with_say_statements")` returns `completed` with final state
- `engine.jump()` behavior is unchanged
- Unknown interaction types yield to IPC even during auto-advance
- Safety counter prevents infinite auto-advance loops and fully cleans up state

---

- [ ] **Unit 3: Fix `exec_code` handling of `CallException`**

**Goal:** When `exec_code` triggers a `CallException` (via game code calling `renpy.call()`), the auto-advance mechanism handles intermediate yields and sends a clean completion response.

**Requirements:** R1, R3

**Dependencies:** Unit 2 (auto-advance mechanism and `completed` status)

**Files:**
- Modify: `src/pytest_renpy/engine/_test_harness.rpy` (exec handler)
- Modify: `src/pytest_renpy/engine/runner.py` (exec_code method)

**Approach:**
- In the harness `exec` command handler: before re-raising `CallException`, record the call stack depth in `_harness_auto_advance_depth`, set `_harness_pending_call_response = True`, reset counter to 0. This activates auto-advance for the internally-called label
- The existing re-raise (`raise`) propagates the exception as before
- On the runner side, `exec_code()` already handles multiple response statuses. Add `completed` handling: when `exec_code` receives `completed`, the exec triggered a call that has finished — return the response normally
- `JumpException` from `exec_code` does NOT activate auto-advance — jumps still yield at every point

**Patterns to follow:**
- Existing `exec` handler pattern in `_harness_command_loop`

**Test scenarios:**
- Happy path: `exec_code("attack_with('hatchet', 'bekri')")` where `attack_with` calls `renpy.call("attack_bekri")` — auto-advances through attack label, returns `completed` with final state (damage applied)
- Happy path: `exec_code("some_function()")` that does NOT trigger navigation — returns `ok` as before
- Happy path: `exec_code("renpy.call('some_label')")` — direct call triggers auto-advance, returns `completed`
- Edge case: `exec_code` triggers `JumpException` — no auto-advance, yields at first interaction point
- Edge case: `exec_code` triggers `CallException` and the called label presents a menu — auto-advance pauses at menu, test must handle `menu_waiting`
- Edge case: `exec_code` triggers `CallException` and the called label has an unknown interaction type — yields to IPC

**Verification:**
- `exec_code("attack_with('hatchet', 'bekri')")` returns without the test needing to manually advance
- Store mutations from the called label are visible immediately after `exec_code` returns
- Non-navigating `exec_code` calls are unaffected

---

- [ ] **Unit 4: Add fallback `start` label for games without one**

**Goal:** Prevent crashes when a jumped-to label returns and execution falls through to Ren'Py's startup flow in games that don't define a `start` label.

**Requirements:** R4

**Dependencies:** Unit 1 (spike determines the mechanism — static label, dynamic registration, or config override)

**Files:**
- Modify: `src/pytest_renpy/engine/_test_harness.rpy`

**Approach:**
- Implement whichever mechanism the spike (Unit 1) proved viable:
  - **If duplicate labels are allowed:** Add `label start:` to the harness that checks `_harness_connected` and redirects to `_harness_idle`. Games with their own `start` label override it at parse time
  - **If duplicate labels error:** Use the alternative mechanism proven in the spike (e.g., dynamic registration via `renpy.game.script.namemap`, `config.after_load_callbacks`, or a label naming convention like `_harness_start_fallback` that the harness redirects to from the init block)
- The fallback must only activate when the harness is connected (not in normal gameplay)
- Test with both: a game that defines `start` (fixture game) and a game that does not (Forest's Bane)

**Patterns to follow:**
- Existing `label splashscreen:` pattern in the harness (conditional redirect based on `_harness_connected`)

**Test scenarios:**
- Happy path: game without `start` label — `engine.jump("some_label")`, label returns, harness catches fallthrough, test can issue next command
- Happy path: game with `start` label — game's behavior is unaffected by the harness
- Edge case: multiple jump+return cycles — harness catches fallthrough each time without stack growth issues

**Verification:**
- Forest's Bane tests no longer crash when a jumped-to label returns
- Fixture game (which defines `start`) continues to work normally

---

### Phase 2: Integration tests

- [ ] **Unit 5: Fixture-game integration tests for auto-advance semantics**

**Goal:** Add targeted fixture-game labels and integration tests that isolate each auto-advance scenario. These tests become the acceptance harness for control-flow semantics, independent of any specific game.

**Requirements:** R1, R2, R3, R5, R6, R7

**Dependencies:** Units 2-3 (auto-advance mechanism)

**Files:**
- Modify: `spike/fixture_game/game/script.rpy` (add test labels)
- Modify: `tests/test_engine.py` (add auto-advance integration tests)

**Approach:**
- Add fixture-game labels that exercise each scenario in isolation:
  - `label call_with_says:` — sets store var, 2 say statements, sets another store var, return
  - `label call_nested:` — calls `call_inner` which has a say and return, then sets a store var, return
  - `label call_with_jump:` — say statement, then `renpy.jump("jump_target")`
  - `label jump_target:` — sets store var, say statement
  - `label call_with_menu:` — say, menu choice, sets store var based on choice, return
  - `label call_no_yields:` — sets store var, return (no say/pause/menu)
  - `label call_with_input:` — say, `renpy.input("name?")`, sets store var (tests unknown interaction type)
- Write integration tests in `tests/test_engine.py` for each scenario:
  - `test_call_auto_advances_says` — call `call_with_says`, verify `completed`, verify both store vars set
  - `test_call_nested_auto_advances` — call `call_nested`, verify `completed`, verify inner and outer store vars
  - `test_call_with_jump_yields` — call `call_with_jump`, verify `yielded` at `jump_target`
  - `test_call_with_menu_pauses` — call `call_with_menu`, verify `menu_waiting`, select, verify `completed`
  - `test_call_no_yields_completes` — call `call_no_yields`, verify `completed`
  - `test_call_with_unknown_type_yields` — call `call_with_input`, verify `yielded` with `yield_type="input"`
  - `test_jump_still_yields_at_every_point` — jump to label with says, verify `yielded` at each
  - `test_exec_code_with_call_completes` — exec code that triggers `renpy.call()`, verify `completed`
  - `test_call_then_jump_no_stale_state` — call completes, then jump yields normally (no auto-advance leak)
  - `test_sequential_calls_both_complete` — two calls in sequence, both return `completed` correctly
  - `test_call_paused_then_jump_cancels` — call hits unknown type, test sends jump, auto-advance cancelled, no stale `completed`

**Patterns to follow:**
- Existing fixture-game test patterns in `tests/test_engine.py`

**Test scenarios:** (each maps to a test listed above, plus lifecycle guards)
- Happy path: call + says → `completed` with final state
- Happy path: call + nested call → `completed` after both return
- Happy path: call + jump → `yielded` at jump target
- Happy path: call + menu → `menu_waiting`, select, `completed`
- Happy path: call + no yields → immediate `completed`
- Happy path: call + unknown interaction type → `yielded`
- Happy path: jump → yields at every point (unchanged)
- Happy path: exec_code triggering call → `completed`
- **Lifecycle: call completes, then jump yields normally** — after `completed` returns, issue a `jump` and verify it yields at every interaction point as usual (no stale auto-advance state)
- **Lifecycle: call completes, then another call completes** — two sequential `call` commands both return `completed` with correct final state (auto-advance state fully resets between calls)
- **Lifecycle: call pauses on unknown/menu, test sends jump, no completed leaks** — call a label that hits an unknown interaction type (or menu), receive the `yielded`/`menu_waiting`, then send `jump` instead of continuing. Verify: auto-advance state is cancelled, jump yields normally, no stale `completed` response arrives later

**Verification:**
- All 11 fixture-game tests pass (8 core + 3 lifecycle guards)
- These tests define the auto-advance contract and will catch regressions
- Lifecycle tests specifically guard against stale auto-advance state leaking across commands

---

- [ ] **Unit 6: Validate with Forest's Bane tests**

**Goal:** Verify the fixes against the 16 failing Forest's Bane tests and simplify the `run_monster_movement` workaround.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Units 2-5 (all mechanism and fixture tests passing)

**Files:**
- Modify: `examples/forests-bane/test_bekri_flow.py`

**Approach:**
- Replace the `run_monster_movement` polling loop with a cleaner pattern that uses `engine.call("move_relevent_monsters")` — auto-advance handles intermediate NA() says, returns when the label completes
- Update combat tests that use `exec_code("attack_with(...)")` — auto-advance handles the internal `renpy.call()` in `attack_with`, so tests can assert on state immediately after `exec_code` returns
- Run the full test suite to verify the 16 failures are resolved
- Note: some tests may still need adjustment if they depend on the `reached_target` sentinel pattern (small Bekri only) — those should be simplified to use `call` semantics instead

**Patterns to follow:**
- Existing test patterns in `test_bekri_flow.py`
- Fixture-game test patterns from Unit 5

**Test scenarios:**
- All `TestSmallBekriMovement` tests pass using `call` instead of jump+advance loop
- All `TestMediumBekriMovement` tests pass — no longer dependent on `reached_target` sentinel
- All `TestLargeBekriMovement` tests pass
- All `TestSmallBekriCombat` tests pass — `exec_code("attack_with(...)")` completes cleanly
- All `TestMediumBekriCombat` tests pass
- All `TestLargeBekriCombat` tests pass
- `TestSeeBekriNarration` and `TestInteractBekri` tests continue to pass
- Menu-based tests (interact_bekri) still work correctly

**Verification:**
- All 16 previously-failing tests pass
- `run_monster_movement` is simplified or removed
- No regressions in passing tests

## System-Wide Impact

- **Interaction graph:** `_patched_ui_interact` gains a conditional branch — auto-advance path (return immediately for safe types) vs. normal IPC yield path (for unknown types or when not in auto-advance). `_patched_display_menu` is unchanged and always yields. `_harness_idle` gains a pre-command-loop check for pending call responses.
- **Error propagation:** `CallException` and `JumpException` propagation is unchanged — auto-advance is purely a yield-point behavior, not an exception-handling change.
- **State lifecycle risks:** Three terminal paths exist for auto-advance state, and all three must clear identical state: (1) normal completion via `_harness_idle` re-entry, (2) jump-from-call via `_patched_ui_interact` depth check, (3) safety counter exceeded. Additionally, navigation commands (`jump`, `call`, `stop`, navigating `exec`) received while paused mid-call must cancel auto-advance before raising their exception, preventing stale state from leaking into the new navigation context.
- **API surface changes:** `engine.call()` gains `yield_type="completed"` as a new return value. `engine.exec_code()` handles `completed` status. `select_menu()` may loop internally when called during an active auto-advance. All runner receiver paths updated to handle the full status vocabulary. `get_store()`, `set_store()`, and `eval_expr()` gain strict status validation — they raise `EngineError` on unexpected navigation statuses instead of silently accepting them.
- **Unchanged invariants:** IPC wire framing (JSON lines), `engine.jump()` semantics, `engine.advance()` semantics, `engine.get_store()` behavior, Layer 1 fixtures.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `_harness_idle` re-entry path may not work as expected after `CallException` | **Unit 1 spike is a hard gate.** Logs exact call stack depth and return node. If re-entry fails, completion signal mechanism must be redesigned before proceeding |
| `renpy.game.context().call_stack` depth semantics differ between raise point and first yield | Unit 1 spike logs depths at both points. Comparison adjusted based on actual delta |
| Ren'Py errors on duplicate `start` label definitions | Unit 1 spike tests this explicitly. Alternative mechanisms ready |
| Auto-advancing unknown interaction types silently corrupts state | Interaction type allowlist — only `say`, `pause`, `with` are auto-advanced. Unknown types yield to IPC. Allowlist is extensible after validation |
| Auto-advance infinite loop if called label never returns | Safety counter with full state cleanup (Unit 2). Counter exceeded → all auto-advance state cleared, normal `yielded` with warning field |
| Nested `renpy.call()` inside a called label | Stack depth increases naturally — auto-advance continues until all nested calls return. Tested explicitly in spike (Unit 1) and fixture game (Unit 5) |
| `select_menu()` during auto-advance receives unexpected `completed` | `select_menu()` loops until terminal response. Protocol fully specified in Key Technical Decisions |
| `_patched_ui_interact` return value is always `True` | Pre-existing issue (not introduced by this plan). Game code depending on interaction return values may behave differently. Out of scope but noted |

## Sources & References

- **Origin document:** [docs/investigations/2026-05-07-renpy-call-and-mid-label-yields.md](docs/investigations/2026-05-07-renpy-call-and-mid-label-yields.md)
- **Layer 2 plan:** [docs/plans/2026-05-06-002-feat-layer2-label-flow-integration-plan.md](docs/plans/2026-05-06-002-feat-layer2-label-flow-integration-plan.md)
- **Bug catalog:** [docs/discovered-bugs.md](docs/discovered-bugs.md)
- Related code: `src/pytest_renpy/engine/_test_harness.rpy`, `src/pytest_renpy/engine/runner.py`
- Fixture game: `spike/fixture_game/game/script.rpy`, `tests/test_engine.py`
- Failing tests: `examples/forests-bane/test_bekri_flow.py` (16 failures)

# Investigation: renpy.call Handling and Mid-Label Yields

**Date:** 2026-05-07
**Status:** Open
**Triggered by:** 16 failing tests in `examples/forests-bane/test_bekri_flow.py`

## Problem

When a test calls `engine.jump("some_label")` or uses `exec_code` to invoke a function that calls `renpy.call()`, the label executes but encounters inline `NA(...)` say statements that yield control back to the test harness via `_patched_ui_interact`. The test reads game state at that yield point, but the code that *modifies* state runs **after** the yield — so the test sees stale values.

### Concrete example: small Bekri movement

In `npc_turns.rpy`, the small Bekri movement block does:

```renpy
$ Entities['monsters']['bekri']['reached_target'] = False
# ... movement logic ...
$ NA("The small Bekri dives underground!", interact=True)
# ^^^ yields here — test regains control
$ Entities['monsters']['bekri']['phase'] = "diving"
# ^^^ hasn't run yet when the test checks phase
```

The test calls `engine.jump("move_relevent_monsters")` and expects `phase` to be `"diving"` after the label completes. But the label hasn't completed — it's paused at the `NA()` yield.

### Workaround for small Bekri

Small Bekri movement sets `reached_target = True` at the end of its block. Tests can loop: advance past each yield, check `reached_target`, stop when it's `True`. This works but is specific to this one code path.

### Medium and large Bekri have no sentinel

Medium and large Bekri movement blocks don't set `reached_target`. There's no generic way to know when the label has "finished its work" versus "paused at an intermediate yield."

## Root cause: `renpy.call` behavior is incomplete

In real Ren'Py, `renpy.call("label")` pushes a return address onto the call stack, executes the label (including all its yields/interactions), and returns to the caller when the label hits `return`. The caller doesn't see intermediate yields — they're handled by Ren'Py's interaction loop.

Our test harness intercepts `renpy.ui.interact` (which handles yields) and immediately returns control to the test. This means:

1. **`engine.jump()`** lands at the label but every yield pauses execution
2. **`engine.call()`** (via `CallException`) starts the label but every yield pauses execution
3. **`exec_code("renpy.call('label')")`** triggers a `CallException` which the harness re-raises, but the same yield problem applies

There is no mechanism to say "execute this label to completion, handling all intermediate yields automatically, and return control to me when the label returns."

## Current infrastructure

### CallException fix (from_current=True)

Ren'Py 8.3.7's `CallException(label, args, kwargs, from_current)` requires `from_current=True` so the return site is the current node (our command loop), not `next_node` which isn't set correctly from within the harness.

### Recursive _harness_idle

After a jumped-to label returns, execution falls through to Ren'Py's `_start` flow which calls `renpy.jump("start")`. Games without a `start` label (like Forest's Bane, which uses `start_run`) crash here. The `_harness_idle` recursive label catches returns and re-enters the command loop:

```renpy
label _harness_idle:
    python:
        _harness_command_loop()
    call _harness_idle from _harness_idle_return
    return
```

This works for `call` but not for `jump` (which has no return site).

### Missing start label handling

The user noted: "in real Ren'Py, it doesn't crash when there is no start label. It just falls through to the first valid label." The actual fallthrough logic in `renpy/common/00start.rpy` needs to be investigated and replicated.

## Open question

> **Is it feasible for "advance through yields until the label returns" to be handled automatically? (Isn't that what Call does?)**

In real Ren'Py, `call some_label` does exactly this: it executes the label, handles all interactions within it (the player clicks through dialogue, makes menu choices), and returns to the calling label when done. The calling label never sees intermediate yields.

For the test harness, this could mean:

- **Option A: Auto-advance mode.** When the harness receives a `call` command, it could automatically advance through all yields (returning `True` from `_patched_ui_interact`) until the call stack depth decreases back to the caller's level. The test would only regain control after the called label returns.

- **Option B: Call-with-continuation.** A new IPC command like `call_and_run` that executes a label and auto-advances, collecting all yielded states along the way, returning them as a batch when the label completes.

- **Option C: Stack-depth tracking.** Track the Ren'Py call stack depth. When `engine.call()` is used, the harness knows the expected return depth and auto-advances intermediate yields until that depth is reached.

Option A or C seem most natural — they mirror what `call` actually does in Ren'Py. The test harness would need to track `renpy.game.context().call_stack` depth and auto-handle yields when executing within a `call` frame.

## Affected tests (16 failing)

| Category | Count | Root cause |
|----------|-------|------------|
| Medium/large Bekri movement | ~5 | No `reached_target` sentinel; yields pause before phase changes |
| Combat with attribute checks | ~6 | `attribute_check()` reads from `CHARACTER_DETAILS` + modifiers, not from `Entities` dict directly; tests set wrong values |
| Combat with `attack_with()` | ~3 | `attack_with()` calls `renpy.call()` which triggers `CallException`; yields in the attack label pause before damage is applied |
| Interact/menu tests | ~2 | Menu options depend on game state set up during yields that haven't completed |

## Next steps

1. Investigate Ren'Py's call stack tracking (`renpy.game.context().call_stack`) to determine feasibility of auto-advance
2. Prototype Option C (stack-depth tracking) in `_patched_ui_interact`
3. Look up actual Ren'Py behavior when no `start` label exists
4. Fix attribute-check tests to use `CHARACTER_DETAILS` / `permanent_attribute_modifier` instead of direct entity dict manipulation
5. Add persistent value stubbing as a formal test helper

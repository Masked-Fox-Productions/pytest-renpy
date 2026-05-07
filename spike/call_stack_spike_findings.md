# Call Stack Spike Findings

**Date:** 2026-05-07

## 1. Call Stack Depth Tracking

**Attribute:** `renpy.game.context().return_stack` (list)

| Point | `len(return_stack)` |
|-------|-------------------|
| Baseline (idle in `_harness_command_loop`) | 2 |
| Inside called label (1 level) | 3 (+1) |
| Inside nested call (2 levels) | 4 (+2) |
| After called label returns | 2 (back to baseline) |
| After nested calls both return | 2 (back to baseline) |

**Delta per call level: +1.**

The baseline of 2 comes from: (1) Ren'Py startup calling `splashscreen`, and (2) `splashscreen` calling `_harness_idle`.

## 2. `_harness_idle` Re-entry After Call Return

**Confirmed.** When a called label returns:
- Execution goes back to the `python:` block in `_harness_idle` (same node ID as baseline)
- `_harness_command_loop()` re-executes
- **No response is sent** — the harness silently re-enters the command loop

This confirms the plan's `_harness_pending_call_response` mechanism is needed. The harness must check a flag on re-entry and send `{"status": "completed"}` before entering the command loop.

## 3. No-yield Call Behavior

When a called label has no yields (no say/pause/menu), it returns immediately. The harness re-enters `_harness_command_loop()` without ever calling `_patched_ui_interact`. The test that sent `call` gets **no response at all** — it times out.

The `_harness_pending_call_response` flag handles this: on `_harness_idle` re-entry, the flag is checked and `completed` is sent regardless of whether any yields occurred.

## 4. Jump Inside Called Label

**IMPORTANT: Jump does NOT pop the call frame.**

| Point | `len(return_stack)` |
|-------|-------------------|
| Baseline | 2 |
| Inside called label (before jump) | 3 |
| At jump target (after jump) | 3 (still +1!) |

The plan assumed depth <= baseline at the jump target. This is **wrong**. The call frame's return address stays on the stack after a jump. The jump target inherits the call frame.

**Implication for auto-advance:** Using depth > baseline as the only auto-advance criterion means auto-advance continues through jump targets. This is acceptable for the current use cases (labels that return), but differs from the plan's design. If the jump target hits `return`, it pops the call frame and auto-advance ends correctly. If the jump target never returns, the safety counter kicks in.

## 5. Exec-Triggered Call

When `exec_code("trigger_call()")` triggers `renpy.call()`:
- `CallException` propagates correctly through the exec handler
- No response is sent before the propagation (existing bug per plan)
- Depth is +1 inside the called label
- Called label yields work normally

The auto-advance mechanism handles this case identically to direct `call` — the exec handler must record depth and set the pending flag before re-raising `CallException`.

## 6. Duplicate Label Behavior

**Ren'Py errors on duplicate labels.** Adding `label start:` to both the harness and the game causes a compile error:
```
The label start is defined twice, at File "game/_test_harness.rpy", line 255:
label start:
and File "game/script.rpy", line 11:
label start:
```

**Alternative: `config.label_overrides`** — This is a dict that Ren'Py uses to redirect label lookups. Setting `renpy.config.label_overrides['start'] = '_harness_idle'` at init time redirects the `start` label to `_harness_idle`. The harness can conditionally set this override only when the game doesn't define its own `start` label:

```python
if 'start' not in renpy.game.script.namemap:
    renpy.config.label_overrides['start'] = '_harness_idle'
```

## Exit Criteria Mapping

| Criterion | Result |
|-----------|--------|
| Depth delta for called label yields | +1 consistently |
| `_harness_idle` re-enters correctly | Yes — same node, re-executes `_harness_command_loop()` |
| Duplicate labels work | **No** — use `config.label_overrides` instead |
| Jump-from-call depth behavior | **Different from plan** — depth stays at +1, not <= baseline |

## Implementation Adjustments

1. Use `len(renpy.game.context().return_stack)` for depth tracking
2. Record baseline depth BEFORE raising `CallException`
3. In `_patched_ui_interact`: auto-advance when `depth > recorded_baseline`
4. Jump-from-call: accept that auto-advance continues (safety counter is the backstop)
5. Use `config.label_overrides` for fallback start label, not duplicate label
6. `_harness_idle` re-entry sends `completed` when `_harness_pending_call_response` is True

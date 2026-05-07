# Layer 2 Control-Flow Spike Results

## Date: 2026-05-07

## Summary

All three core assumptions validated. The approach works.

## Mechanism: Patched `ui.interact` + `display_menu`

The chosen mechanism patches two functions at the Python level:

1. **`renpy.ui.interact`** — the universal yield point called by `say`, `pause`, `menu`, and all other interaction-producing statements. The patched version sends current state over IPC and blocks for the next command.

2. **`renpy.display_menu`** (+ `renpy.exports.display_menu` + `renpy.store.menu`) — intercepts menu display, sends options over IPC, waits for a selection command, and returns the chosen value without any display.

### Entry Point

`label splashscreen:` runs a Python command loop that blocks on IPC commands. For `jump`/`call`, it raises `JumpException`/`CallException`, which Ren'Py catches and uses to transfer control to the target label. The label executes normally until it hits a yield point (say/pause/menu), where the patched `interact` takes over.

### Key Details

- **Init timing**: Patches applied at `init -999` (earliest). The `display_menu` binding in `renpy.store.menu` must be updated at `init 999` because `defaultstore.py` captures the old reference during init.
- **Guard for pre-connect interactions**: The patched `interact` falls back to the original when the IPC socket isn't connected yet. This handles Ren'Py's GL performance test and other init-time interactions.
- **Performance test**: Disabled via `renpy.config.performance_test = False` to avoid headless display issues.
- **`at_label` format**: Ren'Py's `context().current` returns `[filename, checksum, line_number]`, not a string label name. The real implementation should resolve this to a label name.

## Mechanisms NOT Used

- **Trampoline labels**: Not needed — `JumpException` raised from the command loop or patched `interact` is sufficient.
- **`renpy.call_in_new_context`**: Not needed for the primary flow. May be useful for isolated label execution later.
- **Interaction-cycle callbacks**: Not needed — patching `interact` directly is simpler and works.

## Test Results

| Test | Result | What It Proves |
|------|--------|---------------|
| Boot + Ping | PASS | Headless engine boots with SDL dummy drivers, connects to IPC |
| Jump + Store Mutation | PASS | `JumpException` causes label execution, store mutations observable via IPC |
| Pause Yield | PASS | Patched `interact` fires at `pause`, sends state, blocks for next command |
| Menu Interaction | PASS | Patched `display_menu` sends options, accepts selection, returns value |
| Fresh Process Reset | PASS | Each engine process starts with clean default state |

## Implications for Full Implementation

1. **Units 1-3**: IPC protocol, engine runner, and harness can proceed with this mechanism
2. **Unit 4 (navigation)**: `jump`/`call` via exceptions, `advance` by returning from patched `interact`
3. **Unit 6 (menus)**: `display_menu` patch pattern validated — needs `init 999` for store binding
4. **Unit 7 (isolation)**: Fresh-process isolation works. In-process reset NOT tested (deferred — fresh process is sufficient for v1)
5. **Label name resolution**: `context().current` returns `[file, checksum, line]` — need to resolve to a label name string for the public API

## Open Question Resolved

- **Reset feasibility**: Not tested in this spike. Fresh-process isolation is the v1 approach. Session-scoped reuse remains a stretch goal.

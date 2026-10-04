---
date: 2026-05-07
topic: layer2-dx-improvements
---

# Layer 2 Developer Experience Improvements

## Problem Frame

After building full integration test suites for two Ren'Py games (Kid and King: 78 tests, Forest's Bane: 53 tests), five pain points emerged that would block adoption by other Ren'Py developers:

1. **`call()` vs `jump()` confusion** — The auto-advance behavior baked into `call()` has no Ren'Py precedent. In Ren'Py, `call` means "I expect to return here" and `jump` means "go there permanently." Our `call()` added an unrelated fast-forward side effect, causing 62 test failures in Kid and King when the wrong verb was used.

2. **No dialogue visibility** — Tests can assert on store state and menu options, but not on what the player actually sees. For visual novels where the writing is the product, this is a significant gap.

3. **Boilerplate in every test file** — Example tests manually construct `RenpyEngine` with hardcoded SDK paths and `skipif` marks instead of using the existing `renpy_engine` fixture. The fixture exists but requires CLI flags that aren't discoverable.

4. **Cryptic error messages** — Protocol desync (calling `select_menu` when not at a menu), game crashes (NameError in game code surfacing as "Engine died"), and timeouts all produce unhelpful messages.

5. **Slow test cycles** — Each test boots a fresh Ren'Py process (~2-3 seconds). 78 tests take 3 minutes. A session-reuse mode would cut this dramatically.

## Requirements

**Native Skip Mode**

- R1. Replace the custom auto-advance depth-tracking system with a clean skip mode. The patched `_ui_interact` already functions as the skip mechanism (returning immediately without blocking); decouple this skip behavior from call/jump depth tracking so it applies uniformly.
- R2. Skip mode is enabled by default when the test harness connects. Both `jump()` and `call()` skip through say/pause/with interactions because skip mode is active, not because of verb-specific behavior.
- R3. `call()` and `jump()` return to their standard Ren'Py semantics — `call()` means "push return stack" and `jump()` means "go there." Neither verb implies fast-forward; skip mode (enabled by default per R2) controls whether dialogue is skipped.
- R4. Tests can disable skip mode (`engine.set_skip(False)`) to step through individual say statements, and re-enable it (`engine.set_skip(True)`).
- R5. Remove the 100-interaction auto-advance limit and associated depth-tracking code.

**Dialogue Capture**

- R6. The harness accumulates dialogue during execution — each say statement records who spoke and what they said, even while skipping.
- R7. `engine.get_dialogue()` returns the full accumulated dialogue log since the last reset/clear.
- R8. `engine.get_last_dialogue()` returns the most recent say statement (who + what).
- R9. `engine.clear_dialogue()` clears the accumulated log (useful between test phases).
- R10. Dialogue capture works regardless of skip mode — skipped dialogue is still logged.

**Fixture Polish**

- R11. The `renpy_engine` fixture auto-discovers the Ren'Py SDK via environment variable (`RENPY_SDK_PATH`), then falls back to common installation paths before requiring `--renpy-sdk`.
- R12. Test files can specify their target project path per-file or per-class, so a single test run can exercise multiple games without requiring `--renpy-project` to point at one.

**Better Errors**

- R14. Calling `select_menu()` when not at a menu raises a clear error ("No menu is active — did you mean to jump/call to a label with a menu first?") instead of hanging or desyncing. Both the Python-side `select_menu()` and the harness-side `_harness_command_loop` must validate menu state and return an error when no menu is active.
- R15. When the game itself crashes (Python exception in game code), the error message includes the game's traceback, not just "Engine died."
- R16. Timeout errors include what the engine was waiting for ("Timed out waiting for engine response after jump('label_name')") rather than a generic timeout message.
- R17. When `eval_expr` or `exec_code` fails due to a game-side exception, the error includes the full game-side traceback.

**Session Reuse**

- R18. `engine.reset()` performs a full soft reset: reinitializes all store variables to defaults, returns execution to the idle label, clears the dialogue log, clears pending menu state, and resets the call stack. **Contingent:** R18-R21 depend on the planning-phase investigation into Ren'Py's store-default tracking mechanism succeeding. If full state reset cannot be guaranteed, session reuse may not be feasible.
- R19. After `reset()`, the engine is in the same state as a freshly booted engine — tests that pass with a fresh engine must also pass after a reset.
- R20. The `renpy_engine` fixture can optionally use session reuse (reset between tests instead of restart) for faster test cycles. Note: session reuse applies per-project — tests targeting different projects require separate engine processes regardless.
- R21. Session reuse is opt-in. Tests that need full process isolation can still get it.

## Success Criteria

- A new Ren'Py developer can write their first integration test using only the fixture, without knowing SDK paths or engine lifecycle.
- `call()` and `jump()` behave as a Ren'Py developer expects — the only difference from normal Ren'Py is that dialogue is skipped by default.
- Tests can assert on dialogue content: "After calling the intro label, the boss says 'Welcome aboard.'"
- Error messages tell the developer what went wrong and suggest what to do differently. Specifically: `select_menu()` with no active menu names the issue; game-side crashes include the game's traceback; timeouts name the pending operation.
- A 78-test suite that takes 3 minutes with process-per-test completes significantly faster with session reuse.

## Scope Boundaries

- No changes to Layer 1 (mock-based unit testing). These improvements are Layer 2 only.
- No GUI or visual testing — dialogue capture is text-only (who said what), not screenshot-based.
- No parallel test execution within a single engine process — session reuse is sequential.
- SDK auto-discovery covers Linux and macOS common paths. Windows support is deferred.
- No changes to the IPC protocol wire format — new commands are added within the existing JSON-over-socket protocol.

## Key Decisions

- **Patched interact as skip mechanism**: The patched `_ui_interact` already implements skip behavior by returning immediately without blocking. The fix is to decouple this from call/jump depth tracking — make it a uniform skip mode that both verbs use, remove the auto-advance counter, and let `set_skip(False)` switch to yielding at every interact instead.
- **Dialogue capture approach (gating — needs verification)**: Ren'Py sets `_last_say_who` and `_last_say_what` before the interact call, so the data should be available in the patched interact. If verification shows these aren't reliably set for all say types, the fallback is patching `renpy.exports.say` or `Character.__call__` directly.
- **Skip mode on by default**: The common case for integration tests is "get to the interesting state fast." Tests that care about individual dialogue lines opt into stepping mode.
- **Full soft reset for session reuse**: Partial resets (store-only) would leave stale state in the call stack, dialogue log, or pending menus. A full reset is the only approach that matches fresh-process semantics.

## Dependencies / Assumptions

- `_last_say_who` and `_last_say_what` are set before `ui.interact` is called for all say types (narrator, character, NVL). Needs verification — this gates the dialogue capture approach. Fallback: patch `renpy.exports.say` or `Character.__call__` directly.
- Store defaults can be re-read from Ren'Py's internal default tracking for reset. Needs investigation during planning. This gates R18-R21 (session reuse).

## Outstanding Questions

### Deferred to Planning

- [Affects R18][Needs research] How does Ren'Py track store defaults internally? `renpy.store` has a default mechanism — can we leverage it for reset, or do we need to snapshot defaults at boot?
- [Affects R12][Technical] What's the best mechanism for per-file project paths — a pytest marker (`@pytest.mark.renpy_project(path)`), a module-level variable, or a conftest fixture override?
- [Affects R11][Technical] What common SDK installation paths should be checked on Linux and macOS?

### From 2026-05-07 review

- [Affects R18-R21][Prioritization] Should session reuse be deferred to a future phase? It carries high implementation risk (R19 equivalence guarantee) while solving a convenience problem (3min/78 tests), not an adoption blocker. The other four feature groups are lower risk and higher adoption impact.
- [Affects R12][Scope] Is per-file project path an end-user need or primarily a plugin CI convenience? End-user game developers test their own game; multi-project dispatch may only serve the pytest-renpy maintainer's workflow. Consider whether conftest-level fixture override or separate pytest invocations meet the real need.
- [Affects R20][Scope] Is R20 fixture-level session reuse premature? If R18/R19 deliver a working `reset()` primitive, test authors can call it directly. The fixture-level toggle adds configuration surface and conditional branching without a current consumer that couldn't just call `reset()`.

## Next Steps

-> `/ce-plan` for structured implementation planning

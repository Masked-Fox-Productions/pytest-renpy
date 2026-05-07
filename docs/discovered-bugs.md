# Bugs and Problems Discovered via pytest-renpy

Discovered during Layer 1 implementation and proof-of-concept testing across three Ren'Py projects.

## terminalgame

### `delete_cmd` ignores its category parameter (confirmed bug)

**File:** `game/keyboard.rpy:90-92`

The function signature is `delete_cmd(category, name)` but the body always operates on `cmd_dict['temporary_cmds']`, ignoring the `category` argument entirely:

```python
def delete_cmd(category, name):
    if name in cmd_dict['temporary_cmds']:
        del cmd_dict['temporary_cmds'][name]
```

Callers like `fenton_intro_start_gateway` pass `"temporary"` as the category (not even a valid key — should be `"temporary_cmds"`), but it doesn't matter because the parameter is never used. If anyone called `delete_cmd("base_cmds", "help")`, it would still look in `temporary_cmds`.

**Test:** `examples/terminalgame/test_commands.py::TestDeleteCmd::test_bug_ignores_category_parameter`

### `does_show_character` has Python 3.12 syntax error

**File:** `game/display.rpy:76-92`

The function declares `global in_markup` in two places — first inside an `if` block (line 79), then again at function body level (line 85). Python 3.12 rejects this as "name 'in_markup' is assigned to before global declaration." The code works in Ren'Py's bundled Python 3.9 runtime.

This blocks the entire `init python:` block in display.rpy from loading in Layer 1, which also prevents `game_print`, `handle_end_markup`, `get_character_asset`, `get_font`, and `get_character_modifications` from being available.

### `keyboard.rpy` uses `is` with string literal

**File:** `game/keyboard.rpy:47`

Python warns: `SyntaxWarning: "is" with 'str' literal. Did you mean "=="?` This appears in a string comparison where `==` should be used instead of `is`. Identity comparison on strings is unreliable and version-dependent.

## kid-and-king

### Multi-line `default` not portable

**File:** `game/globals.rpy:14-19`

The `BOOKS` default spans 6 lines:
```renpy
default BOOKS = {
    TAMING_FIRE: "Taming Fire",
    SURVEILLANCE: "Surveillance",
    DYING_GOD: "The Dreams of a Dying God",
    THE_ARCADE: "The Arcade"
}
```

This is valid Ren'Py but not extractable by a single-line parser. Not a bug in the game — it's a parser limitation in Layer 1. Works fine in the actual engine and will work in Layer 2.

## minimum-viable-rpg

### All game logic in label python: blocks

**Not a bug**, but a structural choice that limits Layer 1 testability. All 18 utility functions (combat, inventory, healing) are defined inside `label init_utils: / python:`. All 19 defaults are inside `label start:`. Only `get_base_location()` and the location constants are available via `init python:`.

This is the most common Ren'Py pattern for complex games and is the primary motivation for Layer 2.

## forests-bane

### `reached_target` sentinel only set for small Bekri

**File:** `game/npc_turns.rpy:507-634`

The small Bekri movement block (lines 507-553) sets `Entities['monsters']['bekri']['reached_target'] = False` at the start and `= True` at the end. The medium Bekri block (lines 554-594) and large Bekri block (lines 597-634) do not set this flag at all. If any code depends on `reached_target` for medium or large Bekri, it will read stale data from a previous small Bekri turn or be missing entirely.

Not confirmed as a player-facing bug — the flag may only be consumed in contexts where small Bekri is active. But the inconsistency across sizes is worth noting.

### `attribute_check` uses CHARACTER_DETAILS + modifiers, not Entities dict

**Files:** `game/attribute_check.rpy`, `game/npc_turns.rpy`

The `attribute_check(entity, attribute, difficulty)` function reads base stats from `CHARACTER_DETAILS[character_name]` and adds `permanent_attribute_modifier` values, not from the `Entities` dict directly. Tests that set `Entities["special"]["player"]["grip"] = 999` are manipulating the wrong data structure — the attribute check reads from a different source. Affects 8 tests in test_bekri_flow.py across movement (grip/impression checks) and combat (ranged miss checks, melee dodge).

This requires understanding the game's attribute resolution system (CHARACTER_DETAILS, persistent modifiers, inventory bonuses) to fix correctly — out of scope for the test harness.

### `bekri_eat_arm` — missing `poisoned` key

**File:** `game/npc_turns.rpy`

`Entities["monsters"]["bekri"]` does not have a `poisoned` key by default. The `bekri_eat_arm()` function may set it conditionally, but accessing it unconditionally raises a KeyError. Test `test_eat_arm_consumes_poison_item` needs to use `.get("poisoned", False)` instead.

### `delete_cmd` category parameter also unused here

**File:** `game/keyboard.rpy` (same pattern as terminalgame)

Forest's Bane shares the keyboard command system with terminalgame. The `delete_cmd(category, name)` function ignores its `category` parameter, same as documented under terminalgame above.

## Common across all projects

### gui.rpy / screens.rpy / options.rpy reference Ren'Py internals

All three projects include Ren'Py-generated boilerplate files that reference engine internals (`gui` namespace, `Borders` class, `build` namespace, `_()` translation function, `config` namespace). These fail during Layer 1 loading but are harmless — they're UI configuration, not game logic. The `on_error="skip"` option in the loader handles this gracefully.

"""Layer 1 acceptance tests: Forest's Bane loads with its real data.

Assertions are structural (presence, type, non-emptiness, thresholds) so
routine content changes in the game don't break the plugin's suite. Value
and game-logic tests belong in the Forest's Bane repository.
"""

import sys
import types
from pathlib import Path


def _functions_from(ns, filename):
    return {
        name
        for name, value in ns.items()
        if isinstance(value, types.FunctionType)
        and Path(value.__code__.co_filename).name == filename
    }


# (file relative to game/, exception type) pairs that may fail to load.
ALLOWED_ERRORS = set()
if sys.version_info < (3, 12):
    # damage.rpy:115 nests same-type quotes in an f-string (3.12+ syntax).
    ALLOWED_ERRORS.add(("damage.rpy", "SyntaxError"))


class TestLoadErrors:
    def test_only_allowlisted_errors(self, game, game_dir):
        _, _, errors = game
        unexpected = [
            (item, exc)
            for item, exc in errors
            if (
                Path(item.source_file).relative_to(game_dir).as_posix(),
                type(exc).__name__,
            )
            not in ALLOWED_ERRORS
        ]
        assert unexpected == []


class TestUtilsFunctions:
    def test_label_nested_init_python_loads(self, game):
        """utils.rpy's functions live in `label init_utils:` / `init python:`."""
        ns, _, _ = game
        assert len(_functions_from(ns, "utils.rpy")) >= 150

    def test_long_lived_helpers_callable(self, game):
        ns, _, _ = game
        for name in (
            "get_new_xy",
            "get_all_adjacent_tiles",
            "is_tile_on_map",
            "get_active_entities",
            "summon_entity",
        ):
            assert callable(ns.get(name)), name
        assert ns["is_tile_on_map"](5, 5) in (True, False)


class TestDataTables:
    def test_multiline_tables_are_nonempty_dicts(self, game):
        ns, _, _ = game
        for name in ("CHARACTER_DETAILS", "WEAPONS", "PERK_DETAILS", "item_library"):
            value = ns.get(name)
            assert isinstance(value, dict), name
            assert value, name

    def test_inventory_limit_is_int(self, game):
        ns, _, _ = game
        assert isinstance(ns["MAX_INVENTORY_SPACE"], int)


class TestLabelState:
    def test_init_board_dicts_builds_state(self, project, game):
        ns, _, _ = game
        result = project.run_label_python("init_board_dicts", ns)
        assert result.executed
        for name in ("Entities", "RunStats", "VariableItems"):
            value = ns.get(name)
            assert isinstance(value, dict), name
            assert value, name

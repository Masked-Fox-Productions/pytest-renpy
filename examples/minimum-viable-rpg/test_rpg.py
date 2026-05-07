"""Tests verifying project loading for Minimum Viable RPG.

This project demonstrates:
- Location constants and factory function in init python
- Character defines with Transform positions
- import random in init python blocks
- Credits generation using renpy.version()
- Most game logic in label python: blocks (Layer 2 territory)
"""


class TestProjectLoads:
    def test_game_logic_loads_without_errors(self, game):
        """Only gui/screens/options errors expected (Ren'Py internals)."""
        _, _, errors = game
        game_logic_errors = [
            (b, e) for b, e in errors
            if b and all(
                skip not in b.source_file
                for skip in ("gui.rpy", "screens.rpy", "options.rpy")
            )
        ]
        assert len(game_logic_errors) == 0

    def test_labels_include_locations(self, project):
        label_names = [l.name for l in project.labels]
        assert "start" in label_names
        assert "init_utils" in label_names


class TestLocationConstants:
    def test_location_ids_defined(self, game):
        ns, _, _ = game
        assert ns["CELLAR"] == 0
        assert ns["SCULLERY"] == 1
        assert ns["THRONE_ROOM"] == 2
        assert ns["ROYAL_QUARTERS"] == 3
        assert ns["COURTYARD"] == 4
        assert ns["CHAPEL"] == 5
        assert ns["MARKET"] == 6
        assert ns["FRONTIER"] == 7
        assert ns["FOREST"] == 8
        assert ns["MOUNTAIN"] == 9

    def test_get_base_location_factory(self, game):
        ns, _, _ = game
        loc = ns["get_base_location"]("Test Location")
        assert loc["name"] == "Test Location"
        assert loc["visited"] is False
        assert loc["characters"] == []
        assert loc["monsters"] == []
        assert loc["items"] == []
        assert loc["actions"] == []
        assert loc["exits"] == []

    def test_locations_are_independent(self, game):
        """Each call returns a fresh dict — no shared mutable state."""
        ns, _, _ = game
        loc1 = ns["get_base_location"]("Loc 1")
        loc2 = ns["get_base_location"]("Loc 2")
        loc1["characters"].append("hero")
        assert loc2["characters"] == []


class TestCharacterDefines:
    def test_hero_defined(self, game):
        ns, _, _ = game
        assert ns["HERO"].name == "The Hero"

    def test_all_characters_defined(self, game):
        ns, _, _ = game
        expected = [
            "HERO", "CHEF", "PRINCESS", "MERCHANT", "PRIEST",
            "KING", "RAT", "GOBLIN", "ORC", "DRAKE", "DRAGON",
        ]
        for name in expected:
            assert name in ns, f"Character {name} not defined"
            assert ns[name].name is not None

    def test_transform_positions_defined(self, game):
        ns, _, _ = game
        assert ns["center_left"].xalign == 0.35
        assert ns["center_left"].yalign == 1.0
        assert ns["center_left"].zoom == 0.9
        assert ns["center_right"].xalign == 0.65


class TestRandomImport:
    def test_random_available(self, game):
        ns, _, _ = game
        assert ns["random"] is not None
        assert hasattr(ns["random"], "randint")


class TestCreditsGeneration:
    def test_credits_string_generated(self, game):
        ns, _, _ = game
        assert isinstance(ns["credits_s"], str)

    def test_credits_contain_author(self, game):
        ns, _, _ = game
        assert "Aaron Pogue" in ns["credits_s"]


class TestLayerBoundary:
    """Document what's NOT available in Layer 1 — functions defined in
    label python: blocks require Layer 2 for testing."""

    def test_utility_functions_not_in_namespace(self, game):
        """utils.rpy defines 18 functions inside `label init_utils: / python:`.
        These are Layer 2 territory and not available via init-block loading."""
        ns, _, _ = game
        layer2_functions = [
            "get_combat_damage", "get_spell_damage", "heal_hero",
            "add_item_to_inventory", "remove_item_from_inventory",
            "get_location_by_name", "get_art_tag",
        ]
        for fn_name in layer2_functions:
            assert fn_name not in ns, (
                f"{fn_name} shouldn't be available in Layer 1"
            )

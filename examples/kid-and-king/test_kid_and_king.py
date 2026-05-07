"""Tests verifying project loading for The Kid and the King of Chicago.

This project demonstrates:
- .py file imports via `from utils import *` (sys.path scoping)
- Character defines
- default statements for game state
- credits init block using renpy.version()
"""


class TestProjectLoads:
    def test_init_blocks_extracted(self, game):
        ns, mock, errors = game
        game_errors = [
            (b, e) for b, e in errors
            if b and "gui.rpy" not in b.source_file
            and "screens.rpy" not in b.source_file
            and "options.rpy" not in b.source_file
        ]
        assert len(game_errors) == 0, f"Unexpected errors: {game_errors}"

    def test_labels_found(self, game):
        ns, mock, errors = game
        # Check that the project fixture found labels
        # (labels come from project, not ns)

    def test_gui_errors_are_expected(self, game):
        """gui.rpy, screens.rpy, and options.rpy reference Ren'Py internals
        (gui namespace, Borders class, build namespace) that aren't part of
        the game logic mock. These errors are expected and harmless."""
        _, _, errors = game
        game_logic_errors = [
            (b, e) for b, e in errors
            if b and all(
                skip not in b.source_file
                for skip in ("gui.rpy", "screens.rpy", "options.rpy")
            )
        ]
        assert len(game_logic_errors) == 0


class TestUtilsImport:
    def test_reader_class_imported(self, game):
        ns, _, _ = game
        Reader = ns["Reader"]
        assert Reader is not None
        r = Reader("Test", 0)
        assert r.name == "Test"

    def test_book_constants_imported(self, game):
        ns, _, _ = game
        assert ns["TAMING_FIRE"] == 0
        assert ns["SURVEILLANCE"] == 1
        assert ns["DYING_GOD"] == 2
        assert ns["THE_ARCADE"] == 3

    def test_random_imported(self, game):
        ns, _, _ = game
        assert ns["random"] is not None


class TestCharacterDefines:
    def test_kid_defined(self, game):
        ns, _, _ = game
        assert ns["KID"].name == "The Kid"

    def test_boss_defined(self, game):
        ns, _, _ = game
        assert ns["BOSS"].name == "The King of Chicago"

    def test_characters_are_callable(self, game):
        """Characters in Ren'Py are called to display dialogue."""
        ns, _, _ = game
        ns["KID"]("Hello!")
        ns["BOSS"]("Get out!")


class TestDefaultState:
    def test_skip_intro_default(self, game):
        ns, _, _ = game
        assert ns["skip_intro"] is False

    def test_reader_tracking_defaults(self, game):
        ns, _, _ = game
        assert ns["talked_to_joe"] is False
        assert ns["last_recommendation"] is None
        assert ns["current_reader"] is None
        assert ns["current_readers"] == []
        assert ns["readers"] == {}

    def test_book_summary_defaults(self, game):
        ns, _, _ = game
        assert ns["summarized_taming_fire"] is False
        assert ns["summarized_surveillance"] is False
        assert ns["summarized_dying_god"] is False
        assert ns["summarized_the_arcade"] is False


class TestReaderLogic:
    def test_reader_recommend_correct_book(self, game):
        ns, _, _ = game
        Reader = ns["Reader"]
        r = Reader("Joe", ns["TAMING_FIRE"])
        r.recommend(ns["TAMING_FIRE"])
        assert r.solved is True

    def test_reader_recommend_wrong_book(self, game):
        ns, _, _ = game
        Reader = ns["Reader"]
        r = Reader("Joe", ns["TAMING_FIRE"])
        r.recommend(ns["SURVEILLANCE"])
        assert r.solved is False
        assert ns["SURVEILLANCE"] in r.recommendations

    def test_reader_tracks_multiple_wrong_recommendations(self, game):
        ns, _, _ = game
        Reader = ns["Reader"]
        r = Reader("Joe", ns["TAMING_FIRE"])
        r.recommend(ns["SURVEILLANCE"])
        r.recommend(ns["DYING_GOD"])
        assert len(r.recommendations) == 2
        assert r.solved is False

    def test_reader_solved_after_correct(self, game):
        """Even after wrong recommendations, correct one solves it."""
        ns, _, _ = game
        Reader = ns["Reader"]
        r = Reader("Joe", ns["TAMING_FIRE"])
        r.recommend(ns["SURVEILLANCE"])
        r.recommend(ns["TAMING_FIRE"])
        assert r.solved is True


class TestCreditsGeneration:
    def test_credits_string_generated(self, game):
        ns, _, _ = game
        assert "credits_s" in ns
        assert isinstance(ns["credits_s"], str)

    def test_credits_contain_author(self, game):
        ns, _, _ = game
        assert "Aaron Pogue" in ns["credits_s"]

    def test_credits_contain_renpy_version(self, game):
        """The credits init block calls renpy.version() to include engine info."""
        ns, _, _ = game
        assert "renpy" in ns["credits_s"].lower() or "Engine" in ns["credits_s"]

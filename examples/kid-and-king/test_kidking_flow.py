"""Layer 2 integration tests for The Kid and the King of Chicago.

Tests the book-recommendation puzzle mini-game: 16 readers, 4 books,
break room learning system, conference room selection flow, correct/wrong
recommendation paths, and full game loop.

Requires: Ren'Py SDK and the game at /projects/masked_fox/the-kid-and-the-king-of-chicago
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import RenpyEngine

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
PROJECT_PATH = Path("/projects/masked_fox/the-kid-and-the-king-of-chicago")

requires_sdk = pytest.mark.skipif(not SDK_PATH.exists(), reason="SDK not found")
requires_project = pytest.mark.skipif(
    not PROJECT_PATH.exists(), reason="kid-and-king not found"
)

TAMING_FIRE = 0
SURVEILLANCE = 1
DYING_GOD = 2
THE_ARCADE = 3

BOOK_NAMES = {
    TAMING_FIRE: "Taming Fire",
    SURVEILLANCE: "Surveillance",
    DYING_GOD: "The Dreams of a Dying God",
    THE_ARCADE: "The Arcade",
}

READER_BOOKS = {
    "Joe": TAMING_FIRE, "Ellie": TAMING_FIRE, "Mike": TAMING_FIRE, "Emily": TAMING_FIRE,
    "Chris": SURVEILLANCE, "Sarah": SURVEILLANCE, "Wally": SURVEILLANCE, "Katie": SURVEILLANCE,
    "Martin": DYING_GOD, "Liz": DYING_GOD, "Reggie": DYING_GOD, "Beth": DYING_GOD,
    "Ben": THE_ARCADE, "Katrina": THE_ARCADE, "Luke": THE_ARCADE, "Molly": THE_ARCADE,
}


def make_engine(timeout=30):
    return RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=timeout)


def setup_readers(engine):
    """Call create_readers and return to idle."""
    engine.call("create_readers")


def select_book_from_menu(engine, book_id):
    """At a make_recommendation menu, select the given book."""
    book_text = f"Recommend {BOOK_NAMES[book_id]}"
    options = engine.get_menu_options()
    for i, opt in enumerate(options):
        if opt["text"] == book_text:
            return engine.select_menu(i)
    raise AssertionError(
        f"Book option '{book_text}' not found in menu: "
        f"{[o['text'] for o in options]}"
    )


def recommend_to_reader(engine, reader_name, book_id):
    """Navigate to a reader, recommend a book, and auto-advance through the result.

    Uses engine.call() to auto-advance through dialogue, yielding at the
    make_recommendation menu. After selecting the book, auto-advance continues
    through the recommendation response and back to the next menu.
    """
    result = engine.call(f"talk_to_{reader_name.lower()}")
    if result.raw.get("status") == "menu_waiting":
        return select_book_from_menu(engine, book_id)
    return result


def get_wrong_books(correct_book):
    """Return list of wrong book IDs for a reader."""
    return [b for b in range(4) if b != correct_book]


# ---------------------------------------------------------------------------
# Unit 1: Reader class and game initialization
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestReaderClass:

    def test_reader_created_with_correct_attributes(self):
        with make_engine() as engine:
            setup_readers(engine)
            name = engine.eval_expr('readers["Joe"].name')
            best = engine.eval_expr('readers["Joe"].best_book')
            assert name == "Joe"
            assert best == TAMING_FIRE

    def test_reader_recommend_correct_book_sets_solved(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('readers["Joe"].recommend(0)')
            solved = engine.eval_expr('readers["Joe"].solved')
            assert solved is True

    def test_reader_recommend_wrong_book_appends_to_recommendations(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('readers["Joe"].recommend(1)')
            solved = engine.eval_expr('readers["Joe"].solved')
            recs = engine.eval_expr('len(readers["Joe"].recommendations)')
            assert solved is False
            assert recs == 1

    def test_reader_two_wrong_recommendations(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('readers["Joe"].recommend(1)')
            engine.exec_code('readers["Joe"].recommend(2)')
            solved = engine.eval_expr('readers["Joe"].solved')
            recs = engine.eval_expr('len(readers["Joe"].recommendations)')
            assert solved is False
            assert recs == 2

    def test_create_readers_creates_16_with_correct_books(self):
        with make_engine() as engine:
            setup_readers(engine)
            count = engine.eval_expr('len(readers)')
            assert count == 16
            for name, expected_book in READER_BOOKS.items():
                best = engine.eval_expr(f'readers["{name}"].best_book')
                assert best == expected_book, f"{name} has wrong best_book"


@requires_sdk
@requires_project
class TestGameEntry:

    def test_start_with_intro(self):
        with make_engine() as engine:
            result = engine.jump("start")
            assert result.raw.get("status") == "yielded"
            assert result.yield_type == "say"

    def test_start_skip_intro_reaches_menu(self):
        with make_engine() as engine:
            engine.set_store(skip_intro=True)
            result = engine.call("start")
            assert result.raw.get("status") == "menu_waiting"

    def test_boss_menu_options(self):
        with make_engine() as engine:
            result = engine.call("boss_menu")
            assert result.raw.get("status") == "menu_waiting"
            options = engine.get_menu_options()
            texts = [o["text"] for o in options]
            assert "Review the books" in texts
            assert "Pitch the books" in texts

    def test_boss_menu_review_goes_to_break_room(self):
        with make_engine() as engine:
            engine.call("boss_menu")
            result = engine.select_menu("Review the books")
            assert result.raw.get("status") == "menu_waiting"

    def test_boss_menu_pitch_goes_to_conference_room(self):
        with make_engine() as engine:
            engine.call("boss_menu")
            result = engine.select_menu("Pitch the books")
            assert result.raw.get("status") in ("yielded", "menu_waiting")


# ---------------------------------------------------------------------------
# Unit 2: Break room — book learning system
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestBreakRoom:

    def test_break_room_presents_five_options(self):
        with make_engine() as engine:
            result = engine.call("break_room")
            assert result.raw.get("status") == "menu_waiting"
            options = engine.get_menu_options()
            texts = [o["text"] for o in options]
            assert "Taming Fire" in texts
            assert "Surveillance" in texts
            assert "The Dreams of a Dying God" in texts
            assert "The Arcade" in texts
            assert "I'm ready to make some recommendations!" in texts

    def test_ready_to_recommend_exits(self):
        with make_engine() as engine:
            engine.call("break_room")
            result = engine.select_menu("I'm ready to make some recommendations!")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    @pytest.mark.parametrize("flag_name,menu_text", [
        ("summarized_taming_fire", "Taming Fire"),
        ("summarized_surveillance", "Surveillance"),
        ("summarized_dying_god", "The Dreams of a Dying God"),
        ("summarized_the_arcade", "The Arcade"),
    ])
    def test_first_visit_auto_summarizes(self, flag_name, menu_text):
        with make_engine() as engine:
            assert engine.get_store(flag_name)[flag_name] is False
            engine.call("break_room")
            result = engine.select_menu(menu_text)
            assert result.raw.get("status") == "menu_waiting"
            assert engine.get_store(flag_name)[flag_name] is True

    @pytest.mark.parametrize("flag_name,menu_text", [
        ("summarized_taming_fire", "Taming Fire"),
        ("summarized_surveillance", "Surveillance"),
        ("summarized_dying_god", "The Dreams of a Dying God"),
        ("summarized_the_arcade", "The Arcade"),
    ])
    def test_subsequent_visit_shows_book_options(self, flag_name, menu_text):
        with make_engine() as engine:
            engine.set_store(**{flag_name: True})
            engine.call("break_room")
            result = engine.select_menu(menu_text)
            assert result.raw.get("status") == "menu_waiting"
            options = engine.get_menu_options()
            texts = [o["text"] for o in options]
            assert "Read the back cover" in texts
            assert "Read the first page" in texts
            assert "Choose another book" in texts

    @pytest.mark.parametrize("flag_name,menu_text", [
        ("summarized_taming_fire", "Taming Fire"),
        ("summarized_surveillance", "Surveillance"),
        ("summarized_dying_god", "The Dreams of a Dying God"),
        ("summarized_the_arcade", "The Arcade"),
    ])
    def test_back_cover_returns_to_book_menu(self, flag_name, menu_text):
        with make_engine() as engine:
            engine.set_store(**{flag_name: True})
            engine.call("break_room")
            engine.select_menu(menu_text)
            result = engine.select_menu("Read the back cover")
            assert result.raw.get("status") == "menu_waiting"

    @pytest.mark.parametrize("flag_name,menu_text", [
        ("summarized_taming_fire", "Taming Fire"),
        ("summarized_surveillance", "Surveillance"),
        ("summarized_dying_god", "The Dreams of a Dying God"),
        ("summarized_the_arcade", "The Arcade"),
    ])
    def test_first_page_returns_to_book_menu(self, flag_name, menu_text):
        with make_engine() as engine:
            engine.set_store(**{flag_name: True})
            engine.call("break_room")
            engine.select_menu(menu_text)
            result = engine.select_menu("Read the first page")
            assert result.raw.get("status") == "menu_waiting"

    @pytest.mark.parametrize("flag_name,menu_text", [
        ("summarized_taming_fire", "Taming Fire"),
        ("summarized_surveillance", "Surveillance"),
        ("summarized_dying_god", "The Dreams of a Dying God"),
        ("summarized_the_arcade", "The Arcade"),
    ])
    def test_choose_another_returns_to_break_room(self, flag_name, menu_text):
        with make_engine() as engine:
            engine.set_store(**{flag_name: True})
            engine.call("break_room")
            engine.select_menu(menu_text)
            result = engine.select_menu("Choose another book")
            assert result.raw.get("status") == "menu_waiting"
            texts = [o["text"] for o in engine.get_menu_options()]
            assert "Taming Fire" in texts


# ---------------------------------------------------------------------------
# Unit 3: Conference room — reader creation and selection flow
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestConferenceRoom:

    def test_conference_room_creates_readers(self):
        with make_engine() as engine:
            engine.call("conference_room")
            count = engine.eval_expr('len(readers)')
            assert count == 16

    def test_first_visit_forces_joe(self):
        """First conference_room visit auto-advances to Joe's intro then make_recommendation menu."""
        with make_engine() as engine:
            result = engine.call("conference_room")
            assert result.raw.get("status") == "menu_waiting"
            talked = engine.eval_expr('readers["Joe"].talked_to')
            assert talked is True

    def test_after_joe_shows_reader_selection(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('readers["Joe"].talked_to = True')
            result = engine.call("conference_room")
            assert result.raw.get("status") == "menu_waiting"
            options = engine.get_menu_options()
            texts = [o["text"] for o in options]
            assert any(t in READER_BOOKS for t in texts)

    def test_choose_reader_has_at_most_4_plus_reroll(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('readers["Joe"].talked_to = True')
            engine.call("conference_room")
            options = engine.get_menu_options()
            reader_options = [o for o in options if o["text"] in READER_BOOKS]
            assert 1 <= len(reader_options) <= 4

    def test_one_unsolved_shows_only_that_reader(self):
        with make_engine() as engine:
            setup_readers(engine)
            for name in READER_BOOKS:
                if name != "Ben":
                    engine.exec_code(f'readers["{name}"].solved = True')
            engine.exec_code('readers["Joe"].talked_to = True')
            result = engine.call("conference_room")
            assert result.raw.get("status") == "menu_waiting"
            options = engine.get_menu_options()
            reader_options = [o for o in options if o["text"] in READER_BOOKS]
            assert len(reader_options) == 1
            assert reader_options[0]["text"] == "Ben"

    def test_all_solved_reaches_win(self):
        with make_engine() as engine:
            setup_readers(engine)
            for name in READER_BOOKS:
                engine.exec_code(f'readers["{name}"].solved = True')
            engine.exec_code('readers["Joe"].talked_to = True')
            result = engine.call("conference_room")
            assert result.raw.get("status") in ("yielded", "completed")


# ---------------------------------------------------------------------------
# Unit 4: Correct recommendation for all 16 readers
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestCorrectRecommendations:

    @pytest.mark.parametrize("reader_name,book_id", list(READER_BOOKS.items()))
    def test_correct_recommendation_solves_reader(self, reader_name, book_id):
        with make_engine() as engine:
            setup_readers(engine)
            recommend_to_reader(engine, reader_name, book_id)
            solved = engine.eval_expr(f'readers["{reader_name}"].solved')
            assert solved is True, f"{reader_name} should be solved with {BOOK_NAMES[book_id]}"


# ---------------------------------------------------------------------------
# Unit 5: Wrong recommendations and give-up paths
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestWrongRecommendations:

    @pytest.mark.parametrize("reader_name,book_id", list(READER_BOOKS.items()))
    def test_wrong_recommendation_not_solved(self, reader_name, book_id):
        wrong_book = get_wrong_books(book_id)[0]
        with make_engine() as engine:
            setup_readers(engine)
            recommend_to_reader(engine, reader_name, wrong_book)
            solved = engine.eval_expr(f'readers["{reader_name}"].solved')
            recs = engine.eval_expr(f'len(readers["{reader_name}"].recommendations)')
            assert solved is False
            assert recs == 1

    @pytest.mark.parametrize("reader_name,book_id", [
        ("Joe", TAMING_FIRE),
        ("Ben", THE_ARCADE),
        ("Martin", DYING_GOD),
        ("Katie", SURVEILLANCE),
    ])
    def test_give_up_after_two_wrong(self, reader_name, book_id):
        wrong_books = get_wrong_books(book_id)
        with make_engine() as engine:
            setup_readers(engine)
            recommend_to_reader(engine, reader_name, wrong_books[0])
            recommend_to_reader(engine, reader_name, wrong_books[1])
            solved = engine.eval_expr(f'readers["{reader_name}"].solved')
            recs = engine.eval_expr(f'len(readers["{reader_name}"].recommendations)')
            assert solved is False
            assert recs == 2

    def test_come_back_later_returns_to_conference(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('current_reader = readers["Joe"]')
            result = engine.call("make_recommendation")
            assert result.raw.get("status") == "menu_waiting"
            result = engine.select_menu("Come back later")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_remind_me_returns_to_recommendation_menu(self):
        with make_engine() as engine:
            setup_readers(engine)
            engine.exec_code('current_reader = readers["Joe"]')
            engine.exec_code('current_reader.talked_to = True')
            result = engine.call("make_recommendation")
            assert result.raw.get("status") == "menu_waiting"
            result = engine.select_menu("Remind me what you like")
            assert result.raw.get("status") == "menu_waiting"


# ---------------------------------------------------------------------------
# Unit 6: Full game loop — intro through win
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestFullGameLoop:

    def test_win_game_label(self):
        with make_engine() as engine:
            setup_readers(engine)
            for name in READER_BOOKS:
                engine.exec_code(f'readers["{name}"].solved = True')
            result = engine.jump("win_game")
            assert result.raw.get("status") == "yielded"

    def test_full_playthrough(self):
        """Play the entire game: skip intro, solve all 16 readers, reach win."""
        with make_engine(timeout=120) as engine:
            engine.set_store(skip_intro=True)
            result = engine.call("start")
            assert result.raw.get("status") == "menu_waiting"

            engine.select_menu("Pitch the books")

            reader_name = engine.eval_expr("current_reader.name")
            assert reader_name == "Joe"
            select_book_from_menu(engine, READER_BOOKS["Joe"])

            for _ in range(16):
                unsolved = engine.eval_expr(
                    '[r for r in readers if not readers[r].solved]'
                )
                if not unsolved:
                    break

                result = engine.call("conference_room")
                assert result.raw.get("status") == "menu_waiting"

                options = engine.get_menu_options()
                texts = [o["text"] for o in options]

                reader_name = None
                for text in texts:
                    if text in READER_BOOKS:
                        reader_name = text
                        break
                assert reader_name is not None, f"No reader found in menu: {texts}"

                engine.select_menu(reader_name)
                select_book_from_menu(engine, READER_BOOKS[reader_name])

            all_solved = engine.eval_expr(
                'all(readers[r].solved for r in readers)'
            )
            assert all_solved is True

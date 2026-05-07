---
title: "feat: Kid and King of Chicago — full coverage Layer 2 integration tests"
type: feat
status: active
date: 2026-05-07
---

# Kid and King of Chicago — Full Coverage Layer 2 Integration Tests

## Overview

Add comprehensive Layer 2 integration tests for *The Kid and the King of Chicago*, a Ren'Py visual novel with a book-recommendation puzzle mini-game. The game has ~2,800 lines of logic across 77 labels, 16 NPC readers, and 4 books. Its simple, well-structured design makes it an ideal candidate for approaching 100% code coverage of game logic through the pytest-renpy engine.

## Problem Frame

The existing test file (`examples/kid-and-king/test_kidking_flow.py`) has only 2 tests — a smoke test for `start` and a basic reader creation check. The game's logic is entirely deterministic (no random attribute checks, no combat RNG), meaning every branch can be exercised with the right sequence of menu selections. This makes it the strongest proof-of-concept for pytest-renpy's ability to deliver near-complete coverage of a real Ren'Py game.

## Requirements Trace

- R1. Test every reachable label in the game (77 labels)
- R2. Test every menu choice branch (break room books, reader selection, book recommendations)
- R3. Test correct recommendation for all 16 readers (happy path)
- R4. Test wrong recommendation rejection dialogue for all 16 readers × 3 wrong books
- R5. Test the "give up after 2 wrong" path for at least a representative sample of readers
- R6. Test the full game loop: intro → break room → conference room → win → credits
- R7. Test the skip_intro flag and boss_menu paths
- R8. Test Reader class state transitions (talked_to, solved, recommendations list)
- R9. Test conference room scene changes based on unsolved reader count
- R10. Test edge cases: "Come back later", "Remind me what you like", re-roll reader selection

## Scope Boundaries

- No testing of gui.rpy, screens.rpy, options.rpy (Ren'Py boilerplate)
- No testing of visual presentation (show/hide/scene commands, image display)
- No testing of screen_credits.rpy scroll animation (ATL transforms require display)
- No modifications to the game code — tests exercise the game as-is

## Context & Research

### Relevant Code and Patterns

- `examples/forests-bane/test_bekri_flow.py` — Established pattern: `make_engine()`, `init_game()`, helper functions, class-based test organization, `exec_code` for state setup, `eval_expr` for assertions
- `src/pytest_renpy/engine/runner.py` — `RenpyEngine` API: `jump`, `call`, `advance`, `select_menu`, `get_store`, `set_store`, `exec_code`, `eval_expr`, `get_menu_options`
- `examples/kid-and-king/test_kidking_flow.py` — Existing starter file with boilerplate and 2 smoke tests

### Game Architecture Summary

**Flow:** `start` → `intro_dialogue` → `boss_menu` → `break_room` (learn books) → `conference_room` (recommend loop) → `win_game` → `end_credits`

**Core mechanics:**
- 4 books (constants 0-3): Taming Fire, Surveillance, Dreams of a Dying God, The Arcade
- 16 Reader NPCs, each with one `best_book`; `Reader.recommend(book)` sets `solved=True` on match or appends to `recommendations` on mismatch
- Conference room forces Joe first, then random selection of up to 4 unsolved readers
- `make_recommendation` uses `renpy.display_menu()` to present un-rejected books
- `handle_recommendation_<name>` branches on correct/each-wrong-book/give-up (≥2 wrong)
- Break room: 4 books × 3 views each (summary, back cover, first page) + "ready to recommend"

**Reader→Book mapping:**
| Book | Readers |
|------|---------|
| Taming Fire (0) | Joe, Ellie, Mike, Emily |
| Surveillance (1) | Chris, Sarah, Wally, Katie |
| Dying God (2) | Martin, Liz, Reggie, Beth |
| The Arcade (3) | Ben, Katrina, Luke, Molly |

### Institutional Learnings

- `engine.call()` auto-advances through say/pause/with interactions; yields at menus and unknown types
- `exec_code` with `renpy.call()` inside also triggers auto-advance (CallException path)
- Conference room uses `renpy.display_menu()` (not Ren'Py `menu:` statement) for dynamic reader selection — this maps to the harness's `_patched_display_menu` and works with `select_menu`
- `make_recommendation` also uses `renpy.display_menu()` for book choices
- Random seed is fixed to 0 by the harness, so `random.shuffle` in `choose_a_reader` is deterministic

## Key Technical Decisions

- **Test organization by game system**: Group tests into classes by system (Reader class, break room, conference room flow, per-reader recommendations, full game loop) rather than by label. This matches the Forest's Bane pattern and keeps related assertions together.

- **Helper functions for common flows**: Extract `init_game()`, `setup_readers()`, `recommend_book(engine, reader_name, book)` to avoid duplicating the multi-step menu interaction sequence across 60+ recommendation tests.

- **Parametrize reader recommendation tests**: Use `@pytest.mark.parametrize` for the 16 correct recommendations and the 48 wrong-book rejections. Each reader follows the same `talk_to → make_recommendation → handle_recommendation` flow, differing only in the book constant and expected dialogue outcome.

- **Test wrong recommendations via state assertions, not dialogue text**: Assert on `reader.solved == False` and `len(reader.recommendations)` rather than matching exact dialogue strings. This makes tests resilient to copy edits while still verifying the game logic.

- **Conference room scene thresholds via eval_expr**: The scene changes at boundaries (0, 1, 2-4, 5-7, 8-10, 11-13, 14+). Test by solving specific numbers of readers and checking `len(unsolved_readers)`.

- **Full game loop as capstone test**: One test that plays the entire game correctly (skip intro, solve all 16 readers) and verifies the win condition. This exercises the complete flow including the conference room loop, random reader selection, and win_game transition.

## Implementation Units

- [ ] **Unit 1: Test infrastructure and Reader class tests**

  **Goal:** Replace the starter file with proper test infrastructure and unit-level tests for the Reader class and game initialization.

  **Requirements:** R7, R8

  **Dependencies:** None

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - Follow the Forest's Bane pattern: `make_engine()`, `requires_sdk`, `requires_project` decorators
  - `init_game(engine)` helper that jumps to `start` with `skip_intro=True` (set via `set_store` before jump)
  - `setup_readers(engine)` helper that calls `create_readers` and returns
  - Test `Reader.__init__`, `Reader.recommend` correct book, `Reader.recommend` wrong book via `exec_code` and `eval_expr`
  - Test `start` with `skip_intro=False` yields at intro dialogue
  - Test `start` with `skip_intro=True` skips to `boss_menu`
  - Test `boss_menu` presents two choices and both navigate correctly

  **Patterns to follow:**
  - `examples/forests-bane/test_bekri_flow.py` lines 1-80 (boilerplate, helpers)

  **Test scenarios:**
  - Happy path: Reader created with correct name and best_book
  - Happy path: Reader.recommend(best_book) sets solved=True
  - Happy path: Reader.recommend(wrong_book) appends to recommendations, solved stays False
  - Happy path: start with skip_intro=False reaches intro dialogue (yields at say)
  - Happy path: start with skip_intro=True reaches boss_menu (yields at menu)
  - Happy path: boss_menu "Review the books" navigates to break_room
  - Happy path: boss_menu "Pitch the books" navigates to conference_room
  - Edge case: Reader.recommend called twice with wrong books — recommendations has length 2, solved still False
  - Edge case: create_readers creates exactly 16 readers with correct book assignments

  **Verification:** 9+ tests pass covering Reader state and game entry paths

- [ ] **Unit 2: Break room — book learning system**

  **Goal:** Test all break room navigation: 4 books × 3 content views, summary flag tracking, and "ready to recommend" exit.

  **Requirements:** R1, R2

  **Dependencies:** Unit 1

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - Jump directly to `break_room` label; it presents a Ren'Py `menu:` statement (5 options)
  - Each book label checks `summarized_<book>` flag — first visit auto-jumps to summary, subsequent visits show the 4-option menu
  - Test each book's first visit (auto-summary), then verify the flag is set, then test each sub-menu option (back cover, first page, review summary, choose another book)
  - Use `get_store` to verify `summarized_*` flags
  - The book content labels all end with `jump <book_label>` which re-presents the menu — verify the menu appears after each content view

  **Patterns to follow:**
  - Forest's Bane `TestSeeBekriNarration` class — checking that labels yield without crashing

  **Test scenarios:**
  - Happy path: break_room presents 5 menu options (4 books + ready)
  - Happy path: Selecting "Taming Fire" first time → auto-jumps to summary → sets summarized_taming_fire=True → returns to taming_fire menu
  - Happy path: Selecting "Taming Fire" after summary → shows 4 options (back, first, summary, choose another)
  - Happy path: "Read the back cover" → content displays → returns to book menu
  - Happy path: "Read the first page" → content displays → returns to book menu
  - Happy path: "Review the summary" → re-displays summary → returns to book menu
  - Happy path: "Choose another book" → returns to break_room menu
  - Happy path: "I'm ready to make some recommendations!" → navigates to conference_room
  - Integration: Repeat pattern for all 4 books (parametrize: taming_fire, surveillance, dying_god, the_arcade)
  - Edge case: summarized flag persists across multiple break_room visits

  **Verification:** All 4 books testable through their summary/back/first paths; flags tracked correctly

- [ ] **Unit 3: Conference room — reader creation and selection flow**

  **Goal:** Test conference room initialization, reader creation, Joe-first forced path, and random reader selection menu.

  **Requirements:** R1, R2, R9, R10

  **Dependencies:** Unit 1

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - `conference_room` label auto-calls `create_readers` if `readers` dict is empty
  - First visit forces `talk_to_joe` (Joe hasn't been talked to)
  - After Joe is talked to, `choose_a_reader` presents up to 4 shuffled unsolved readers + "try someone else" option
  - The `renpy.display_menu()` call in `choose_a_reader` works with the harness menu system
  - Scene thresholds: test by solving N readers, then jumping to `conference_room` and checking unsolved count
  - "Try someone else" option (value -1) re-rolls the reader selection

  **Patterns to follow:**
  - Forest's Bane `TestInteractBekri` class — menu option verification

  **Test scenarios:**
  - Happy path: conference_room with empty readers dict → creates 16 readers → forces Joe
  - Happy path: conference_room after Joe talked_to → presents choose_a_reader menu
  - Happy path: choose_a_reader shows ≤4 reader names + "try someone else"
  - Happy path: Selecting a reader name navigates to their talk_to label
  - Happy path: "try someone else" re-rolls reader selection (menu appears again)
  - Integration: Scene threshold — 16 unsolved readers shows conference_room_6
  - Integration: Scene threshold — 1 unsolved reader shows conference_room_1
  - Integration: Scene threshold — 0 unsolved readers shows conference_room (empty)
  - Edge case: choose_a_reader with exactly 4 unsolved shows all 4 (no shuffle truncation)
  - Edge case: choose_a_reader with 1 unsolved shows only that reader + "try someone else"

  **Verification:** Conference room initialization, Joe-first path, and reader selection all work

- [ ] **Unit 4: Correct recommendation for all 16 readers**

  **Goal:** Test the happy path for every reader — recommend their best_book and verify they accept it.

  **Requirements:** R3, R8

  **Dependencies:** Unit 1, Unit 3

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - Helper function `recommend_to_reader(engine, reader_name, book_id)`:
    1. Set `current_reader` to the reader via `exec_code`
    2. Jump to `talk_to_<name>` (triggers intro if not talked to, then jumps to `make_recommendation`)
    3. At the `make_recommendation` menu, select the book option by matching text ("Recommend Taming Fire", etc.)
    4. Auto-advance through `handle_recommendation_<name>` (solved path has say statements, then jumps to conference_room)
    5. Verify `readers[name].solved == True` via `eval_expr`
  - Parametrize across all 16 readers with their correct book
  - The `make_recommendation` menu uses `renpy.display_menu()` which the harness intercepts
  - Menu option format is `("Recommend {BOOKS[book]}", book)` — select by matching text prefix

  **Patterns to follow:**
  - Forest's Bane parametrized tests (e.g., `TestBekriSizeInit::test_size_sets_correct_stats`)

  **Test scenarios:**
  - Happy path: Recommend Taming Fire to Joe → solved=True (parametrize for all 4 Taming Fire readers)
  - Happy path: Recommend Surveillance to Chris → solved=True (parametrize for all 4 Surveillance readers)
  - Happy path: Recommend Dying God to Martin → solved=True (parametrize for all 4 Dying God readers)
  - Happy path: Recommend The Arcade to Ben → solved=True (parametrize for all 4 Arcade readers)

  **Verification:** All 16 readers accept their correct book; `solved` flag set for each

- [ ] **Unit 5: Wrong recommendations and give-up paths**

  **Goal:** Test wrong-book rejection dialogue triggers and the give-up-after-2-wrong path.

  **Requirements:** R4, R5, R8

  **Dependencies:** Unit 4

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - Each reader has 3 wrong books. `handle_recommendation_<name>` has explicit `elif` branches for each wrong book (with distinct rejection dialogue) plus a give-up check at the bottom.
  - Test wrong recommendation: recommend wrong book → verify `solved==False`, `len(recommendations)==1`, flow returns to `make_recommendation`
  - Test give-up: recommend 2 wrong books sequentially → verify `len(recommendations)==2`, flow jumps to `conference_room` (reader gives up)
  - Parametrize: test at least one wrong book per reader (16 tests), plus give-up for a representative sample (4 readers, one per book group)
  - The tricky part: after a wrong recommendation, the label jumps back to `make_recommendation` which presents a menu. The test needs to handle this second menu (either select another book or verify the menu appears).

  **Patterns to follow:**
  - Forest's Bane `TestSmallBekriCombat::test_melee_misses_when_airborne` — testing negative outcomes

  **Test scenarios:**
  - Error path: Recommend Surveillance to Joe → solved=False, recommendations=[1]
  - Error path: Recommend Dying God to Joe → solved=False, recommendations=[2]
  - Error path: Recommend The Arcade to Joe → solved=False, recommendations=[3]
  - Error path: Parametrize one wrong recommendation per reader (16 tests total)
  - Edge case: Give-up path — recommend 2 wrong books to Joe → len(recommendations)==2, returns to conference_room
  - Edge case: Give-up path — recommend 2 wrong books to Ben → same pattern
  - Edge case: Give-up path — recommend 2 wrong books to Martin → same pattern
  - Edge case: Give-up path — recommend 2 wrong books to Katie → same pattern
  - Edge case: After give-up, reader is NOT solved but CAN be re-attempted (not explicitly blocked in code)
  - Integration: "Remind me what you like" option in make_recommendation → calls <name>_intro → returns to make_recommendation
  - Integration: "Come back later" option → returns to conference_room

  **Verification:** All wrong-book rejection branches exercised; give-up threshold at 2 confirmed

- [ ] **Unit 6: Full game loop — intro through win**

  **Goal:** Test the complete game playthrough from start to win_game, solving all 16 readers.

  **Requirements:** R6

  **Dependencies:** Units 1-5

  **Files:**
  - Modify: `examples/kid-and-king/test_kidking_flow.py`

  **Approach:**
  - One integration test that plays the entire game:
    1. Jump to `start` (skip_intro=True for speed)
    2. At boss_menu, select "Pitch the books"
    3. Conference room forces Joe first — recommend Taming Fire
    4. Loop: at choose_a_reader menu, select a reader, recommend their correct book
    5. After all 16 solved, conference_room detects 0 unsolved → jumps to win_game
    6. Verify win_game dialogue yields
  - This is the capstone test proving the full integration works
  - The reader selection is randomized (but seed=0), so the test needs to handle whatever readers appear by looking up their correct book from a mapping dict
  - Alternative: use `exec_code` to directly solve readers and test win detection, for a faster version

  **Patterns to follow:**
  - The overall "play the game" integration test pattern

  **Test scenarios:**
  - Integration: Full game loop — skip intro, solve all 16 readers via conference room, reach win_game
  - Integration: Full game loop with intro — play through intro_dialogue, boss_menu "Review the books", visit one book in break room, then proceed to conference room and solve all readers
  - Happy path: win_game label yields with expected dialogue
  - Edge case: Solve 15 readers, verify conference_room still loops; solve the 16th, verify win_game triggers

  **Verification:** Complete game playthrough succeeds; win condition reached after all 16 readers solved

## System-Wide Impact

- **Interaction graph:** Tests exercise `renpy.display_menu()` interception (both Ren'Py `menu:` in break room and Python `renpy.display_menu()` in conference room/make_recommendation), `renpy.call()` from make_recommendation's "remind me" path, and `renpy.jump()` from choose_a_reader's dynamic jump
- **Error propagation:** No error paths in the game itself — all paths lead to either conference_room loop or win_game
- **State lifecycle risks:** Reader objects persist across the conference_room loop. Tests that modify reader state (recommendations, solved) within one engine session affect subsequent interactions
- **API surface parity:** N/A — single-player game with no external API
- **Integration coverage:** The full game loop test (Unit 6) proves that the harness correctly handles: Ren'Py `menu:` → `renpy.display_menu()` → `renpy.call()` from Python → `renpy.jump()` from Python → auto-advance through say statements → loop re-entry
- **Unchanged invariants:** The game code is not modified. All tests are read-only observers of game behavior.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `renpy.display_menu()` in `choose_a_reader` uses dynamic Python-built options — harness may not intercept correctly | Already proven in existing test_kidking_flow.py and Forest's Bane tests; `_patched_display_menu` handles this |
| `renpy.call()` inside `make_recommendation`'s "remind me" path (Python-level call) may not return cleanly | The auto-advance handles CallException from Python code; tested in engine test_exec_code_with_call_completes |
| `renpy.jump()` inside `choose_a_reader` (Python f-string jump) may behave differently from label `jump` | Both raise JumpException; harness handles this identically |
| Full game loop test may be slow (16 reader interactions × engine IPC) | Accept ~60s runtime; use skip_intro and direct recommendations to minimize say-statement volume |
| `random.shuffle` in `choose_a_reader` with seed=0 produces a fixed order — test must handle that specific order | Build a `READER_BOOKS` lookup dict so the test can recommend the correct book regardless of selection order |

## Sources & References

- Game source: `/projects/masked_fox/the-kid-and-the-king-of-chicago/game/`
- Engine API: `src/pytest_renpy/engine/runner.py`
- Pattern reference: `examples/forests-bane/test_bekri_flow.py`
- Existing starter: `examples/kid-and-king/test_kidking_flow.py`

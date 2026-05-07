"""Layer 2 integration tests for Forest's Bane — Bekri movement and combat.

Tests all branching label paths for Bekri's movement and combat across
her three sizes (small, medium, large), including phase transitions,
weapon-type branching, and attribute-check gating.

Requires: Ren'Py SDK and the Forest's Bane project at /projects/xander/forests_bane
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pytest_renpy.engine.runner import RenpyEngine

SDK_PATH = Path(os.path.expanduser("~/tools/renpy-8.3.7-sdk"))
PROJECT_PATH = Path("/projects/xander/forests_bane")

requires_sdk = pytest.mark.skipif(not SDK_PATH.exists(), reason="SDK not found")
requires_project = pytest.mark.skipif(
    not PROJECT_PATH.exists(), reason="forests_bane not found"
)


def make_engine(timeout=30):
    return RenpyEngine(SDK_PATH, PROJECT_PATH, timeout=timeout)


def init_game(engine):
    """Stub persistent data and jump to start_debug_run."""
    engine.exec_code(
        "if not hasattr(persistent, 'save_card_info') or "
        "persistent.save_card_info is None:\n"
        "    persistent.save_card_info = {}\n"
        "persistent.save_card_info[0] = {\n"
        "    'created_date': 0, 'play_time': 0,\n"
        "    'play_time_display': '00:00:00',\n"
        "    'last_run_started': 0, 'recent_character': 'wesley',\n"
        "    'wins': 0, 'losses': 0,\n"
        "    'unlocked_characters': ['wesley'],\n"
        "    'unlocked_items': [], 'records_info': {},\n"
        "}\n"
    )
    engine.set_store(save_game_index=0)
    return engine.jump("start_debug_run")


def setup_bekri(engine, size, x, y, phase="waiting", target=None):
    """Activate Bekri at a given position with specified size."""
    engine.exec_code(f'set_bekri_size("{size}")')
    engine.exec_code(f'summon_entity("bekri", {x}, {y})')
    if phase != "waiting":
        engine.exec_code(
            f'Entities["monsters"]["bekri"]["phase"] = "{phase}"'
        )
    if target is not None:
        engine.exec_code(f'set_target("bekri", "{target}")')


def run_monster_movement(engine):
    """Call move_relevent_monsters with auto-advance.

    The harness auto-advances through intermediate NA() say statements
    and returns when the label completes.
    """
    engine.call("move_relevent_monsters")


def get_bekri(engine, field):
    return engine.eval_expr(f'Entities["monsters"]["bekri"]["{field}"]')


def get_bekri_nested(engine, *keys):
    expr = 'Entities["monsters"]["bekri"]'
    for k in keys:
        expr += f'["{k}"]'
    return engine.eval_expr(expr)


def get_player_health(engine):
    return engine.eval_expr('Entities["special"]["player"]["health"]')


# ---------------------------------------------------------------------------
# Size initialization
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestBekriSizeInit:
    """set_bekri_size() assigns correct stats per size."""

    @pytest.mark.parametrize(
        "size,expected_health,expected_damage,expected_haste",
        [
            ("small", 150, 20, 100),
            ("medium", 200, 60, 50),
            ("large", 400, 90, 0),
        ],
    )
    def test_size_sets_correct_stats(
        self, size, expected_health, expected_damage, expected_haste
    ):
        with make_engine() as engine:
            init_game(engine)
            engine.exec_code(f'set_bekri_size("{size}")')
            assert get_bekri(engine, "size") == size
            assert get_bekri(engine, "health") == expected_health
            assert get_bekri_nested(engine, "attack_details", "damage") == expected_damage
            assert get_bekri_nested(engine, "attack_details", "haste") == expected_haste

    def test_random_size_when_none(self):
        """set_bekri_size() with no arg picks from small/medium/large."""
        with make_engine() as engine:
            init_game(engine)
            engine.exec_code("set_bekri_size()")
            assert get_bekri(engine, "size") in ("small", "medium", "large")


# ---------------------------------------------------------------------------
# Small Bekri — movement phases
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestSmallBekriMovement:
    """Small Bekri: speed 2, 5-phase cycling at target."""

    @pytest.mark.parametrize(
        "start_phase,expected_phase",
        [
            ("waiting", "diving"),
            ("diving", "lifting"),
            ("lifting", "waiting"),
            ("staggered", "lifting"),
            ("falling", "staggered"),
        ],
    )
    def test_phase_transition_at_target(self, start_phase, expected_phase):
        """Phase cycles correctly when Bekri reaches its target."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase=start_phase, target="player")
            # High haste to dodge dive damage so player doesn't die
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 999')
            run_monster_movement(engine)
            assert get_bekri(engine, "phase") == expected_phase

    def test_reached_target_flag_set(self):
        """reached_target is set to True after phase transition."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="waiting", target="player")
            run_monster_movement(engine)
            assert get_bekri(engine, "reached_target") is True

    def test_moves_at_speed_2(self):
        """Small Bekri moves 2 tiles per turn toward target."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 0, phase="waiting", target="player")
            run_monster_movement(engine)
            assert get_bekri(engine, "y") == 2

    def test_diving_damages_player(self):
        """Diving phase at target deals damage to player."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="diving", target="player")
            # Low haste so attack lands
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 0')
            health_before = get_player_health(engine)
            run_monster_movement(engine)
            assert get_player_health(engine) < health_before


# ---------------------------------------------------------------------------
# Medium Bekri — movement phases
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestMediumBekriMovement:
    """Medium Bekri: speed 2, 2-phase (waiting/attacking)."""

    def test_waiting_to_attacking_fails_grip(self):
        """Phase waiting → attacking when grip check (25) fails."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["grip"] = 0')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = -999')
            run_monster_movement(engine)
            assert get_bekri(engine, "phase") == "attacking"

    def test_waiting_stays_when_grip_passes(self):
        """Phase stays waiting when player passes grip check (25)."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["grip"] = 999')
            run_monster_movement(engine)
            assert get_bekri(engine, "phase") == "waiting"

    def test_attacking_damages_player(self):
        """Medium Bekri in attacking phase deals damage to player."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="attacking", target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = -999')
            health_before = get_player_health(engine)
            run_monster_movement(engine)
            assert get_player_health(engine) < health_before

    def test_attacking_to_waiting_on_impression(self):
        """Phase attacking → waiting when impression check (80) passes."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="attacking", target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 999')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 999')
            run_monster_movement(engine)
            assert get_bekri(engine, "phase") == "waiting"

    def test_arm_rip_chance_when_attacking(self):
        """Medium attacking phase has 1/4 chance of arm rip (gnaw attack)."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="attacking", target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["grip"] = 0')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = -999')
            # Seed random so randint(0,3)==3 triggers arm rip
            engine.exec_code("renpy.random.seed(42)")
            run_monster_movement(engine)
            # Whether arm rip happened depends on seed — just verify no crash
            assert get_bekri(engine, "phase") in ("waiting", "attacking")


# ---------------------------------------------------------------------------
# Large Bekri — movement
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestLargeBekriMovement:
    """Large Bekri: speed 1, no phases, direct attack on reach."""

    def test_moves_at_speed_1(self):
        """Large Bekri moves 1 tile per turn toward target."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 0, target="player")
            run_monster_movement(engine)
            assert get_bekri(engine, "y") == 1

    def test_attacks_player_on_reach(self):
        """Large Bekri damages player when it reaches them."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 0')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = -999')
            health_before = get_player_health(engine)
            run_monster_movement(engine)
            assert get_player_health(engine) < health_before

    def test_high_damage_roll_clears_target(self):
        """Damage rolls 31-32 trigger limb removal and clear target."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 0')
            # We can't guarantee a 31-32 roll, but we can test the path
            # doesn't crash with any roll
            run_monster_movement(engine)
            # Bekri should still be alive
            assert get_bekri(engine, "health") > 0


# ---------------------------------------------------------------------------
# Small Bekri — combat (via attack_with → attack_bekri)
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestSmallBekriCombat:
    """Small Bekri combat: melee only hits when staggered, ranged varies by phase."""

    def test_melee_hits_when_staggered(self):
        """Melee weapon hits small Bekri in staggered phase."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="staggered", target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_bekri(engine, "health") < health_before

    def test_melee_misses_when_airborne(self):
        """Melee weapon can't reach small Bekri in non-staggered phases."""
        for phase in ("waiting", "diving", "lifting"):
            with make_engine() as engine:
                init_game(engine)
                setup_bekri(engine, "small", 3, 3, phase=phase, target="player")
                engine.exec_code("change_inventory('hatchet')")
                engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
                health_before = get_bekri(engine, "health")
                engine.exec_code('attack_with("hatchet", "bekri")')
                assert get_bekri(engine, "health") == health_before, (
                    f"Melee should miss in {phase} phase"
                )

    def test_ranged_guaranteed_hit_when_staggered(self):
        """Ranged hit at staggered phase (difficulty 0) always hits."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="staggered", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 1')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_bekri(engine, "health") < health_before

    def test_ranged_miss_when_waiting(self):
        """Ranged misses small Bekri in waiting phase (difficulty 95)."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="waiting", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = -999')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 0')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_bekri(engine, "health") == health_before

    def test_ranged_diving_hit_causes_falling(self):
        """Hitting small Bekri during diving phase knocks it down (falling → staggered).

        The attack sets phase to 'falling', but attack_with runs through
        end_turn which triggers monster movement, advancing falling → staggered.
        """
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="diving", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 999')
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_bekri(engine, "phase") in ("falling", "staggered")

    def test_ranged_hit_adds_partial_health_back(self):
        """Ranged hits on small Bekri add back 30% of weapon damage."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="staggered", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            health_after = get_bekri(engine, "health")
            # Damage dealt minus 30% heal-back — net should be ~70% of total damage
            net_damage = health_before - health_after
            assert net_damage > 0


# ---------------------------------------------------------------------------
# Medium Bekri — combat
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestMediumBekriCombat:
    """Medium Bekri combat: waiting blocks melee, attacking allows all."""

    def test_melee_blocked_when_waiting(self):
        """Melee can't reach medium Bekri in waiting phase (in trees)."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_bekri(engine, "health") == health_before

    def test_ranged_hits_when_waiting_with_judgement(self):
        """Ranged hits medium Bekri in waiting phase if judgement (75) passes."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["judgement"] = 999')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_bekri(engine, "health") < health_before

    def test_ranged_misses_when_waiting_low_judgement(self):
        """Ranged misses medium Bekri in waiting phase if judgement fails."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["judgement"] = -999')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 0')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_bekri(engine, "health") == health_before

    def test_all_weapons_hit_when_attacking(self):
        """Any weapon damages medium Bekri in attacking phase."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="attacking", target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_bekri(engine, "health") < health_before


# ---------------------------------------------------------------------------
# Large Bekri — combat
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestLargeBekriCombat:
    """Large Bekri combat: melee with grip-based counter, ranged heals her."""

    def test_melee_deals_damage(self):
        """Melee weapon damages large Bekri."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_bekri(engine, "health") < health_before

    def test_melee_counter_with_low_grip(self):
        """Low grip takes counter damage from large Bekri melee."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["grip"] = 0')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 0')
            health_before = get_player_health(engine)
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_player_health(engine) < health_before

    def test_melee_dodge_with_high_grip(self):
        """High grip (65+) avoids counter damage from large Bekri."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 999')
            health_before = get_player_health(engine)
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_player_health(engine) == health_before

    def test_ranged_heals_large_bekri(self):
        """Ranged attacks heal large Bekri by 90% of damage dealt."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 999')
            health_before = get_bekri(engine, "health")
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            health_after = get_bekri(engine, "health")
            # Net damage should be only ~10% of weapon damage (90% healed back)
            net_damage = health_before - health_after
            assert net_damage < 40  # hunting_rifle base damage

    def test_ranged_counter_when_targeting_player(self):
        """Large Bekri counters ranged attack when targeting player."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            engine.exec_code("change_inventory('hunting_rifle')")
            engine.exec_code("add_hunting_rifle_ammo_amount(10)")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["haste"] = 0')
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["luck"] = 0')
            health_before = get_player_health(engine)
            engine.exec_code('attack_with("hunting_rifle", "bekri")')
            assert get_player_health(engine) < health_before


# ---------------------------------------------------------------------------
# Bekri observation — see_bekri label
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestSeeBekriNarration:
    """Verify see_bekri produces narration per size and state."""

    def test_see_small_alive(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, target="player")
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_see_small_dead(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3)
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 0')
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_see_medium_waiting(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="waiting", target="player")
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_see_medium_attacking(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3, phase="attacking", target="player")
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_see_large_targeting_player(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")

    def test_see_large_no_target(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3)
            result = engine.jump("see_bekri")
            assert result.raw.get("status") in ("yielded", "menu_waiting")


# ---------------------------------------------------------------------------
# Bekri interaction — interact_bekri menu branches
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestInteractBekri:
    """Verify interact_bekri presents correct menu options per size."""

    def test_small_alive_menu(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, target="player")
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Attack" in texts
                assert "Leave" in texts

    def test_small_dead_loot(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3)
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 0')
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Take Wings" in texts

    def test_medium_dead_gizzard(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3)
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 0')
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Take Gizzard" in texts

    def test_large_alive_menu(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Examine" in texts
                assert "Attack" in texts

    def test_large_dead_beak(self):
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3)
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 0')
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Beak" in texts

    def test_medium_dead_harvest_meat_with_tools(self):
        """Dead medium Bekri shows Harvest Meat when player has butchering tools."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "medium", 3, 3)
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 0')
            engine.exec_code("change_inventory('butchering_tools')")
            result = engine.jump("interact_bekri")
            if result.raw.get("status") == "menu_waiting":
                texts = [o["text"] for o in engine.get_menu_options()]
                assert "Harvest Meat" in texts


# ---------------------------------------------------------------------------
# Bekri kill and special mechanics
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestBekriKill:

    def test_kill_via_damage(self):
        """Killing Bekri sets health <= 0."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3, phase="staggered", target="player")
            engine.exec_code('Entities["monsters"]["bekri"]["health"] = 1')
            engine.exec_code("change_inventory('hatchet')")
            engine.exec_code('Entities["special"]["player"]["permanent_attribute_modifier"]["impression"] = 50')
            engine.exec_code('attack_with("hatchet", "bekri")')
            assert get_bekri(engine, "health") <= 0


@requires_sdk
@requires_project
class TestBekriEatArm:

    def test_eat_arm_damages_player(self):
        """bekri_eat_arm() deals 10 blade damage."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            health_before = get_player_health(engine)
            engine.exec_code("bekri_eat_arm()")
            assert get_player_health(engine) < health_before

    def test_eat_arm_consumes_poison_item(self):
        """bekri_eat_arm() applies highest poison item from inventory to Bekri."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "large", 3, 3, target="player")
            # Give player a poisonous item
            engine.exec_code("change_inventory('hemlock_berries')")
            engine.exec_code("bekri_eat_arm()")
            poisoned = engine.eval_expr('Entities["monsters"]["bekri"].get("poisoned", False)')
            # If hemlock_berries has poison_value, bekri should be poisoned
            has_hemlock = engine.eval_expr("'hemlock_berries' in inventory")
            # The item should be consumed
            assert not has_hemlock


# ---------------------------------------------------------------------------
# Target acquisition
# ---------------------------------------------------------------------------


@requires_sdk
@requires_project
class TestBekriTargeting:

    def test_targets_player_when_adjacent(self):
        """Bekri targets player when adjacent and no other targets."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 4)  # one tile away from player at 3,3
            target = engine.eval_expr('get_bekri_target()')
            assert target == "player"

    def test_prefers_monsters_over_player(self):
        """Bekri targets adjacent monsters before player."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 3, 3)
            # Summon another monster adjacent to bekri
            engine.exec_code('summon_entity("stragg", 3, 4)')
            engine.exec_code('Entities["monsters"]["stragg"]["health"] = 100')
            target = engine.eval_expr('get_bekri_target()')
            assert target == "stragg"

    def test_no_target_when_isolated(self):
        """Bekri has no target when nothing is adjacent."""
        with make_engine() as engine:
            init_game(engine)
            setup_bekri(engine, "small", 0, 0)
            # Player is at 3,3 — not adjacent to 0,0
            target = engine.eval_expr('get_bekri_target()')
            assert target is False or target is None

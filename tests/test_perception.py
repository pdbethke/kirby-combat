"""Combat perception tests (spec 2026-06-13-combat-perception-design §1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant

# Committed in-repo fixture (same one test_hero_combatant_skeleton uses).
INFERNA_HDC = Path(__file__).parent / "fixtures" / "Inferna.hdc"


def _inferna() -> HeroCombatant:
    if not INFERNA_HDC.exists():
        pytest.skip(f"HDC fixture not present: {INFERNA_HDC}")
    return HeroCombatant.from_hdc(str(INFERNA_HDC))


def test_every_character_has_normal_sight():
    senses = _inferna().senses()
    sight = [s for s in senses if s.xmlid == "NORMALSIGHT"]
    assert len(sight) == 1
    assert sight[0].group == "sight"
    assert sight[0].is_targeting is True


def test_inferna_has_infrared_in_the_sight_group():
    # Inferna.hdc carries INFRAREDPERCEPTION (a Sight-Group targeting sense).
    senses = _inferna().senses()
    ir = [s for s in senses if s.xmlid == "INFRAREDPERCEPTION"]
    assert len(ir) == 1
    assert ir[0].group == "sight"          # IR is bought into the Sight Group
    assert ir[0].is_targeting is True


def test_senses_are_targeting_only_set():
    # senses() returns only Targeting senses (the combat-relevant ones).
    for s in _inferna().senses():
        assert s.is_targeting is True


# --- Task 2: PER + Stealth roll helpers ---------------------------------------

from kirby_combat.perception import per_roll_target, _roll_3d6_succeeds
from kirby_combat.dice import RandomRoller


def test_per_target_is_9_plus_int_over_5():
    hc = _inferna()
    int_val = int(hc.hero.characteristic_value("INT"))
    assert per_roll_target(hc) == 9 + int_val // 5


def test_skill_roll_value_returns_none_when_absent():
    # A character without STEALTH returns None (caller treats as auto-perceived).
    hc = _inferna()
    val = hc.skill_roll_value("DEFINITELY_NOT_A_SKILL")
    assert val is None


def test_3d6_succeeds_is_roll_le_target():
    # roller seeded so the 3d6 is deterministic; success iff sum <= target.
    r = RandomRoller(seed=1)
    rolled = sum(RandomRoller(seed=1).roll_dice(3))   # same seed → same roll
    assert _roll_3d6_succeeds(target=rolled, roller=r) is True
    r2 = RandomRoller(seed=1)
    assert _roll_3d6_succeeds(target=rolled - 1, roller=r2) is False


# --- Task 3: invisibility_groups(hero) ----------------------------------------

from kirby_combat.perception import invisibility_groups, SIGHT, HEARING, SMELL


def test_no_invisibility_power_means_no_groups():
    assert invisibility_groups(_inferna().hero) == frozenset()


def test_invisibility_defaults_to_sight_group():
    # A synthetic hero with an INVISIBILITY power and no parseable group adder
    # defaults to the Sight Group (the HERO default).
    class _P:
        xmlid = "INVISIBILITY"; alias = "Invisibility"; adders = []; sub_powers = []
    class _H:
        powers = [_P()]
    assert invisibility_groups(_H()) == frozenset({SIGHT})


def test_invisibility_reads_real_option_and_adder_groups():
    # Real shape (HSB Ghost): primary group in power.option_id == "SIGHTGROUP",
    # extra groups as assigned_adders with XMLID "HEARINGGROUP"/"SMELLGROUP".
    class _Adder:
        def __init__(self, xmlid, alias):
            self.XMLID = xmlid
            self.alias = alias
    class _P:
        xmlid = "INVISIBILITY"
        alias = "Invisibility"
        option_id = "SIGHTGROUP"
        assigned_adders = [
            _Adder("NOFRINGE", "No Fringe"),
            _Adder("HEARINGGROUP", "Hearing Group"),
            _Adder("SMELLGROUP", "Smell/Taste Group"),
        ]
    class _H:
        powers = [_P()]
    assert invisibility_groups(_H()) == frozenset({SIGHT, HEARING, SMELL})


# --- Task 4: Perception + perceive() LoS/occlusion core ------------------------

from kirby_combat.perception import perceive, Perception
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Wall,
)


def _wall(x: float = 10.0, height: float = 3.0) -> Wall:
    # Mirrors tests/test_attack_los.py's _wall: a tall LoS-blocking wall.
    return Wall(
        id="w", name="Brick",
        segment=(Position(x, 0, 0), Position(x, 10, 0)),
        height_m=height, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )


def _two_combatant_scene(observer, target, *, wall: bool = False) -> Scene:
    # Observer at (0,5,1.5), target at (20,5,1.5); optional wall at x=10
    # (same geometry test_attack_los.py uses to (un)block LoS).
    # Two Inferna loads share the HDC-derived id "inferna"; give them distinct
    # session ids so combatant_positions doesn't collapse to one entry.
    observer.id, target.id = "observer", "target"
    return Scene(
        id="s1", name="Perception",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[],
        walls=[_wall(x=10.0, height=3.0)] if wall else [],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={
            observer.id: Position(0, 5, 1.5),
            target.id: Position(20, 5, 1.5),
        },
    )


def test_perceive_clear_los_is_targetable_via_sight():
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=False)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True
    assert "normal_sight" in p.via or "NORMALSIGHT" in p.via


def test_perceive_occluded_by_wall_is_not_physically_targetable():
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=True)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is False
    assert p.kind == "occluded"

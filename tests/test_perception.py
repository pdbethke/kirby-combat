"""Combat perception tests (spec 2026-06-13-combat-perception-design §1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant

# Committed in-repo fixture (same one test_hero_combatant_skeleton uses).
INFERNA_HDC = Path(__file__).parent / "fixtures" / "Inferna.hdc"


def _inferna() -> HeroCombatant:
    # hero_designer is an OPTIONAL integration dep — kirby-combat CI does not
    # install it (the engine consumes a LoadedHero supplied by the consumer).
    # Guard like test_hero_combatant_skeleton's from_hdc tests so the module's
    # HDC-loading tests skip cleanly in CI; the pure-synthetic perception tests
    # (Mind Scan, surprise, contests) carry no HDC dep and still run.
    pytest.importorskip("hero_designer")
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


def test_occluded_perception_carries_real_wall_id():
    # Fix I2: occluder_id must be the blocking wall's real id, not "occluded".
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=True)
    # The wall helper builds a wall with id="w".
    p = perceive(obs, tgt, scene)
    assert p.kind == "occluded"
    assert p.occluder_id == "w"


def test_no_scene_means_no_occluder_id():
    # Fix I2: scene-less / no-position call → occluder_id is None (no gate).
    obs, tgt = _inferna(), _inferna()
    p = perceive(obs, tgt, None)
    assert p.occluder_id is None


# --- Task 5: Invisibility per-group + Fringe + Stealth-vs-PER contest ----------


class _StubSensePower:
    """One sense power for a synthetic observer hero (mirrors the loaded
    power's duck-type: ``.xmlid`` + ``.sub_powers`` + adder accessors)."""

    def __init__(self, xmlid: str):
        self.xmlid = xmlid
        self.alias = xmlid.title()
        self.assigned_adders: list = []
        self.adders: list = []
        self.sub_powers: list = []


class _StubObserverHero:
    """Minimal LoadedHero stand-in exposing ``.powers`` (one sense power),
    ``.skills`` and ``.characteristic_value`` — enough for ``senses()`` and
    ``per_roll_target``. INT defaults to 10 → PER target 11."""

    def __init__(self, xmlid: str, *, int_val: int = 10):
        self.name = f"Observer<{xmlid}>"
        self.powers = [_StubSensePower(xmlid)]
        self.skills: list = []
        self.talents: list = []
        self._int = int_val

    def characteristic_value(self, xmlid: str) -> int:
        return {"INT": self._int}.get(xmlid.upper(), 0)


def _hero_with_sense(xmlid: str) -> HeroCombatant:
    """A HeroCombatant whose only bought sense is ``xmlid`` (plus the
    always-present Normal Sight). Distinct id so positions don't collapse."""
    from kirby_combat.hero_view import HeroCombatState

    return HeroCombatant(
        id="observer",
        hero=_StubObserverHero(xmlid),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )


def _two_combatant_scene_adjacent(observer, target, *, gap_m: float = 1.0) -> Scene:
    # Observer at (0,5,1.5), target gap_m away along x — no wall.
    observer.id, target.id = "observer", "target"
    return Scene(
        id="s2", name="PerceptionAdjacent",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={
            observer.id: Position(0, 5, 1.5),
            target.id: Position(gap_m, 5, 1.5),
        },
    )


def test_sight_invisible_target_not_seen_by_sight_but_seen_by_radar():
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=False)
    # obs has only Sight-group senses → sight-invisible target is unperceived
    # (20m apart, so the Fringe doesn't apply).
    p = perceive(obs, tgt, scene, target_invisible=True)
    assert p.targetable_physical is False
    assert p.kind == "invisible"
    # ...but give the observer a Radar (non-Sight group) sense → perceived.
    obs_radar = _hero_with_sense("RADAR")
    obs_radar.id = "observer"
    scene2 = _two_combatant_scene(obs_radar, tgt, wall=False)
    p2 = perceive(obs_radar, tgt, scene2, target_invisible=True)
    assert p2.targetable_physical is True
    assert "radar" in p2.via


def test_fringe_perceivable_within_2m():
    # An Invisible target within 2m is perceivable via the Fringe (PER roll).
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=1.0)  # ≤2m apart
    # seed=2 → 3d6 = 3 ≤ PER target 11 → Fringe spotted.
    p = perceive(obs, tgt, scene, target_invisible=True, roller=RandomRoller(seed=2))
    assert p.targetable_physical is True
    assert "fringe" in p.detail


def test_no_fringe_invisibility_is_not_spotted_within_2m():
    # An Invisibility with the No Fringe adder gives no Fringe to perceive.
    obs = _inferna()

    class _Inv:
        xmlid = "INVISIBILITY"
        alias = "Invisibility"
        option_id = "SIGHTGROUP"

        class _NoFringe:
            XMLID = "NOFRINGE"
            alias = "No Fringe"

        assigned_adders = [_NoFringe()]
        sub_powers: list = []

    class _Tgt:
        name = "Ghost"
        powers = [_Inv()]
        skills: list = []
        talents: list = []

        def characteristic_value(self, xmlid):
            return 10

    from kirby_combat.hero_view import HeroCombatState

    tgt = HeroCombatant(
        id="target", hero=_Tgt(),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=1.0)
    p = perceive(obs, tgt, scene, target_invisible=True, roller=RandomRoller(seed=2))
    assert p.targetable_physical is False
    assert p.kind == "invisible"


def test_hidden_target_runs_stealth_contest():
    obs, tgt = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=False)
    # target hidden; if no STEALTH skill → auto-perceived (no contest to win)
    p = perceive(obs, tgt, scene, target_hidden=True, roller=RandomRoller(seed=3))
    assert p.targetable_physical is True   # Inferna has no STEALTH → can't actually hide


# --- Task 6: Mind Scan / mental-LOS gate + is_surprised -----------------------

from kirby_combat.perception import is_surprised


class _TalentStub:
    """One talent on a synthetic hero (duck-types the loaded talent: ``.xmlid``)."""

    def __init__(self, xmlid: str):
        self.xmlid = xmlid
        self.alias = xmlid.replace("_", " ").title()


class _StubTalentHero:
    """Minimal LoadedHero stand-in carrying one talent (e.g. DANGER_SENSE) plus
    Normal Sight only. INT defaults to 10 → PER target 11."""

    def __init__(self, talent_xmlid: str, *, int_val: int = 10):
        self.name = f"Talented<{talent_xmlid}>"
        self.powers: list = []
        self.skills: list = []
        self.talents = [_TalentStub(talent_xmlid)]
        self._int = int_val

    def characteristic_value(self, xmlid: str) -> int:
        return {"INT": self._int}.get(xmlid.upper(), 0)


def _hero_with_talent(xmlid: str) -> HeroCombatant:
    """A HeroCombatant whose only talent is ``xmlid`` (e.g. DANGER_SENSE)."""
    from kirby_combat.hero_view import HeroCombatState

    return HeroCombatant(
        id="observer",
        hero=_StubTalentHero(xmlid),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )


def test_mind_scan_perceives_through_a_wall_mentally():
    obs = _hero_with_sense("MINDSCAN")
    tgt = _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=True)   # sight blocked
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    p = perceive(obs, tgt, scene, target_invisible=True)  # sight-invisible too
    assert p.targetable_physical is False      # can't punch/shoot
    assert p.targetable_mental is True         # mental LOS via Mind Scan
    assert "mindscan" in p.via


def test_is_surprised_true_when_unperceived_and_no_danger_sense():
    obs, attacker = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, attacker, wall=True)  # observer can't see attacker
    assert is_surprised(observer=obs, attacker=attacker, scene=scene) is True


def test_danger_sense_negates_surprise():
    obs = _hero_with_talent("DANGER_SENSE")
    attacker = _inferna()
    scene = _two_combatant_scene(obs, attacker, wall=True)
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    assert is_surprised(observer=obs, attacker=attacker, scene=scene) is False


def test_hidden_cheshire_runs_real_stealth_contest():
    # Cheshire HAS Stealth (roll target 11) → a real opposed 3d6 contest runs
    # and the rolls are surfaced in detail.
    obs = _inferna()
    cheshire_hdc = Path(
        "/home/pdbethke/Documents/Champions/Docs/Champions_Villain_Teams_"
        "Character_Pack/Champions Villains 2 6E ƒ/GRAB/CHESHIRE_CAT-CV2.hdc"
    )
    if not cheshire_hdc.exists():
        pytest.skip(f"Cheshire HDC not present: {cheshire_hdc}")
    tgt = HeroCombatant.from_hdc(str(cheshire_hdc))
    obs.id, tgt.id = "observer", "target"
    scene = Scene(
        id="s3", name="StealthContest",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={
            "observer": Position(0, 5, 1.5),
            "target": Position(20, 5, 1.5),
        },
    )
    p = perceive(obs, tgt, scene, target_hidden=True, roller=RandomRoller(seed=3))
    assert "stealth" in p.detail
    assert p.detail["stealth"] == 11


# --- Fix I3: Combat Sense seam ------------------------------------------------

from kirby_combat.perception import has_combat_sense
from kirby_combat.perception import MENTAL


def test_has_combat_sense_true_for_a_combat_sense_hero():
    # A hero carrying COMBAT_SENSE (talent) surfaces the seam as True.
    hc = _hero_with_talent("COMBAT_SENSE")
    assert has_combat_sense(hc.hero) is True
    assert hc.has_combat_sense() is True


def test_has_combat_sense_false_for_inferna():
    hc = _inferna()
    assert has_combat_sense(hc.hero) is False
    assert hc.has_combat_sense() is False


# --- Fix M4: is_surprised must see the attacker's concealment ------------------


def test_is_surprised_true_for_invisible_attacker():
    # An Invisible attacker the observer can't otherwise perceive (Sight-only
    # observer, no wall) → surprised, because is_surprised now threads the
    # attacker's Invisibility into perceive().
    obs, attacker = _inferna(), _inferna()
    scene = _two_combatant_scene(obs, attacker, wall=False)
    assert is_surprised(
        observer=obs, attacker=attacker, scene=scene,
        attacker_invisible=True,
    ) is True


def test_is_surprised_false_when_nonsight_sense_perceives_invisible_attacker():
    # Same Invisible (Sight-group) attacker, but the observer has Radar (a
    # non-Sight sense) → perceives → not surprised.
    obs_radar = _hero_with_sense("RADAR")
    attacker = _inferna()
    obs_radar.id, attacker.id = "observer", "target"
    scene = Scene(
        id="s4", name="SurpriseInvisible",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={
            "observer": Position(0, 5, 1.5),
            "target": Position(20, 5, 1.5),
        },
    )
    assert is_surprised(
        observer=obs_radar, attacker=attacker, scene=scene,
        attacker_invisible=True,
    ) is False


# --- Test gaps: mental Invisibility vs Mind Scan; Penetrative through wall -----


def test_mental_invisibility_blocks_mind_scan():
    # A target whose Invisibility covers the MENTAL group can't be Mind Scanned.
    obs = _hero_with_sense("MINDSCAN")

    class _Inv:
        xmlid = "INVISIBILITY"
        alias = "Invisibility"
        option_id = "MENTALGROUP"
        assigned_adders: list = []
        sub_powers: list = []

    class _Tgt:
        name = "MindCloaked"
        powers = [_Inv()]
        skills: list = []
        talents: list = []

        def characteristic_value(self, xmlid):
            return 10

    from kirby_combat.hero_view import HeroCombatState

    tgt = HeroCombatant(
        id="target", hero=_Tgt(),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )
    # Sanity: the build's Invisibility covers MENTAL.
    assert invisibility_groups(tgt.hero) == frozenset({MENTAL})
    # Put a wall between them so Sight is occluded — the ONLY possible mental
    # channel is Mind Scan, which the MENTAL-group Invisibility must block.
    scene = _two_combatant_scene(obs, tgt, wall=True)
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    p = perceive(obs, tgt, scene, target_invisible=True)
    assert p.targetable_mental is False
    assert "mindscan" not in p.via


class _PenetrativeSensePower:
    """A Spatial-Awareness-style sense power carrying the Penetrative adder."""

    def __init__(self):
        self.xmlid = "SPATIALAWARENESS"
        self.alias = "Spatial Awareness"

        class _Pen:
            XMLID = "PENETRATIVE"
            alias = "Penetrative"
            option_alias = "Penetrative"

        self.assigned_adders = [_Pen()]
        self.adders: list = []
        self.sub_powers: list = []


class _PenetrativeObserverHero:
    def __init__(self, int_val: int = 10):
        self.name = "PenetrativeObserver"
        self.powers = [_PenetrativeSensePower()]
        self.skills: list = []
        self.talents: list = []
        self._int = int_val

    def characteristic_value(self, xmlid: str) -> int:
        return {"INT": self._int}.get(xmlid.upper(), 0)


def test_penetrative_sense_perceives_through_a_wall():
    from kirby_combat.hero_view import HeroCombatState

    obs = HeroCombatant(
        id="observer", hero=_PenetrativeObserverHero(),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )
    # Confirm the Penetrative adder parsed onto the sense.
    spatial = [s for s in obs.senses() if s.xmlid == "SPATIALAWARENESS"]
    assert spatial and spatial[0].penetrative is True
    tgt = _inferna()
    scene = _two_combatant_scene(obs, tgt, wall=True)   # Sight is blocked
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True   # Penetrative sense ignores the wall

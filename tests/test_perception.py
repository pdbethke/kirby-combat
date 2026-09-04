"""Combat perception tests (spec 2026-06-13-combat-perception-design §1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant

from tests.corpus import require_authored



def _real_character() -> HeroCombatant:
    # The HDC-loading perception tests need a real character; the synthetic
    # ones (Mind Scan, surprise, the Stealth contest) carry no such dep and
    # run everywhere. See tests/corpus.py for why no .hdc is committed.
    return HeroCombatant.from_hdc(require_authored("Bokor"))


def test_every_character_has_normal_sight():
    senses = _real_character().senses()
    sight = [s for s in senses if s.xmlid == "NORMALSIGHT"]
    assert len(sight) == 1
    assert sight[0].group == "sight"
    assert sight[0].is_targeting is True


def test_infrared_perception_lands_in_the_sight_group_as_targeting():
    # IR is bought into the Sight Group and is a targeting sense. Stated
    # synthetically: which senses a given character happens to own is not
    # what this asserts.
    senses = _hero_with_sense("INFRAREDPERCEPTION").senses()
    ir = [s for s in senses if s.xmlid == "INFRAREDPERCEPTION"]
    assert len(ir) == 1
    assert ir[0].group == "sight"
    assert ir[0].is_targeting is True


def test_senses_are_targeting_only_set():
    # senses() returns only Targeting senses (the combat-relevant ones).
    for s in _real_character().senses():
        assert s.is_targeting is True


# --- Task 2: PER + Stealth roll helpers ---------------------------------------

from kirby_combat.perception import per_roll_target, _roll_3d6_succeeds
from kirby_dice import RandomRoller


def test_per_target_is_the_engine_s_characteristic_roll():
    """Was `9 + INT // 5`, asserted here in those words -- so the test agreed
    with the code and both were wrong. Truncation is not the rule: an INT of
    13 rolls 12-, and this reported 11-.

    Compared against kirby-cost rather than restated, so the formula has one
    home and this only checks that combat uses it."""
    from kirby_cost.engine.rolls import characteristic_roll
    hc = _real_character()
    int_val = hc.hero.characteristic_value("INT")
    assert per_roll_target(hc) == characteristic_roll(int_val)


def test_per_target_rounds_rather_than_truncates():
    """The distinction the old test could not see. Pinned on values, not on a
    character, so it cannot go quiet if the fixture's INT changes."""
    from kirby_cost.engine.rolls import characteristic_roll
    assert characteristic_roll(13) == 12      # 9 + round(2.6); truncation gives 11
    assert characteristic_roll(18) == 13      # 9 + round(3.6); truncation gives 12
    assert characteristic_roll(15) == 12      # exact multiples agree
    assert characteristic_roll(10) == 11


def test_skill_roll_value_returns_none_when_absent():
    # A character without STEALTH returns None (caller treats as auto-perceived).
    hc = _real_character()
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
    # A hero carrying no INVISIBILITY yields the empty set. Synthetic, so it
    # asserts the derivation rather than one character's power list — a real
    # character that later gains Invisibility would silently invert this.
    class _NoPowers:
        powers: list = []
        skills: list = []
        talents: list = []

    assert invisibility_groups(_NoPowers()) == frozenset()


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
    # Two loads of one character share the HDC-derived id; give them distinct
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
    obs, tgt = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=False)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True
    assert "normal_sight" in p.via or "NORMALSIGHT" in p.via


def test_perceive_occluded_by_wall_is_not_physically_targetable():
    obs, tgt = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=True)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is False
    assert p.kind == "occluded"


def test_occluded_perception_carries_real_wall_id():
    # Fix I2: occluder_id must be the blocking wall's real id, not "occluded".
    obs, tgt = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=True)
    # The wall helper builds a wall with id="w".
    p = perceive(obs, tgt, scene)
    assert p.kind == "occluded"
    assert p.occluder_id == "w"


def test_no_scene_means_no_occluder_id():
    # Fix I2: scene-less / no-position call → occluder_id is None (no gate).
    obs, tgt = _real_character(), _real_character()
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
    obs, tgt = _real_character(), _real_character()
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
    obs, tgt = _real_character(), _real_character()
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=1.0)  # ≤2m apart
    # seed=2 → 3d6 = 3 ≤ PER target 11 → Fringe spotted.
    p = perceive(obs, tgt, scene, target_invisible=True, roller=RandomRoller(seed=2))
    assert p.targetable_physical is True
    assert "fringe" in p.detail


def test_no_fringe_invisibility_is_not_spotted_within_2m():
    # An Invisibility with the No Fringe adder gives no Fringe to perceive.
    obs = _real_character()

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
    obs, tgt = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=False)
    # target hidden; if no STEALTH skill → auto-perceived (no contest to win)
    p = perceive(obs, tgt, scene, target_hidden=True, roller=RandomRoller(seed=3))
    assert p.targetable_physical is True   # no STEALTH → can't actually hide


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
    tgt = _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=True)   # sight blocked
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    p = perceive(obs, tgt, scene, target_invisible=True)  # sight-invisible too
    assert p.targetable_physical is False      # can't punch/shoot
    assert p.targetable_mental is True         # mental LOS via Mind Scan
    assert "mindscan" in p.via


def test_is_surprised_true_when_unperceived_and_no_danger_sense():
    obs, attacker = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, attacker, wall=True)  # observer can't see attacker
    assert is_surprised(observer=obs, attacker=attacker, scene=scene) is True


def test_danger_sense_negates_surprise():
    obs = _hero_with_talent("DANGER_SENSE")
    attacker = _real_character()
    scene = _two_combatant_scene(obs, attacker, wall=True)
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    assert is_surprised(observer=obs, attacker=attacker, scene=scene) is False


class _SkillStub:
    """One skill exposing the ``roll_value`` that ``skill_roll_value`` reads."""

    def __init__(self, xmlid: str, roll_value: int):
        self.xmlid = xmlid
        self.roll_value = roll_value


class _StubStealthyHero:
    """A LoadedHero stand-in carrying Stealth at a known roll target.

    DEX 25 gives Stealth 14- by the standard formula, base skill roll =
    9 + (CHAR/5) (6E1 p57). Stated as data rather than loaded from a
    character file so the test asserts the CONTEST, not a third party's
    published statistics.
    """

    def __init__(self, *, dex: int = 25):
        self.name = "StealthyStub"
        self.powers: list = []
        self.talents: list = []
        self.skills = [_SkillStub("STEALTH", 9 + dex // 5)]
        self._dex = dex

    def characteristic_value(self, xmlid: str) -> int:
        return {"DEX": self._dex}.get(xmlid.upper(), 0)


def _stealthy_hero(*, dex: int = 25) -> HeroCombatant:
    from kirby_combat.hero_view import HeroCombatState

    return HeroCombatant(
        id="target",
        hero=_StubStealthyHero(dex=dex),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )


def test_a_hidden_target_with_stealth_runs_a_real_opposed_contest():
    # A target that HAS Stealth forces a real opposed 3d6 contest, and both
    # rolls are surfaced in detail. DEX 25 -> Stealth 14- (9 + 25/5, 6E1 p57).
    obs = _hero_with_sense("NORMALSIGHT")
    tgt = _stealthy_hero(dex=25)
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
    assert p.detail["stealth"] == 14
    # The contest actually ran: both 3d6 rolls are surfaced, not just targets.
    assert 3 <= p.detail["per_roll"] <= 18
    assert 3 <= p.detail["stealth_roll"] <= 18


def test_the_targets_own_stealth_roll_reaches_the_contest():
    # The engine does not COMPUTE the roll (kirby-cost does, 9 + CHAR/5,
    # 6E1 p57) — it must carry whatever the character actually has into the
    # contest. Three different targets, three different numbers arriving.
    for dex, expected in ((10, 11), (25, 14), (30, 15)):
        obs = _hero_with_sense("NORMALSIGHT")
        tgt = _stealthy_hero(dex=dex)
        obs.id, tgt.id = "observer", "target"
        sc = _two_combatant_scene_adjacent(obs, tgt, gap_m=2.0)
        p = perceive(obs, tgt, sc, target_hidden=True, roller=RandomRoller(seed=3))
        assert p.detail["stealth"] == expected, f"DEX {dex}"


# --- Fix I3: Combat Sense seam ------------------------------------------------

from kirby_combat.perception import has_combat_sense
from kirby_combat.perception import MENTAL


def test_has_combat_sense_true_for_a_combat_sense_hero():
    # A hero carrying COMBAT_SENSE (talent) surfaces the seam as True.
    hc = _hero_with_talent("COMBAT_SENSE")
    assert has_combat_sense(hc.hero) is True
    assert hc.has_combat_sense() is True


def test_has_combat_sense_false_for_real_character():
    hc = _real_character()
    assert has_combat_sense(hc.hero) is False
    assert hc.has_combat_sense() is False


# --- Fix M4: is_surprised must see the attacker's concealment ------------------


def test_is_surprised_true_for_invisible_attacker():
    # An Invisible attacker the observer can't otherwise perceive (Sight-only
    # observer, no wall) → surprised, because is_surprised now threads the
    # attacker's Invisibility into perceive().
    obs, attacker = _real_character(), _real_character()
    scene = _two_combatant_scene(obs, attacker, wall=False)
    assert is_surprised(
        observer=obs, attacker=attacker, scene=scene,
        attacker_invisible=True,
    ) is True


def test_is_surprised_false_when_nonsight_sense_perceives_invisible_attacker():
    # Same Invisible (Sight-group) attacker, but the observer has Radar (a
    # non-Sight sense) → perceives → not surprised.
    obs_radar = _hero_with_sense("RADAR")
    attacker = _real_character()
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
    tgt = _real_character()
    scene = _two_combatant_scene(obs, tgt, wall=True)   # Sight is blocked
    obs.id = "observer"
    scene.combatant_positions["observer"] = Position(0, 5, 1.5)
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True   # Penetrative sense ignores the wall


# --- Range Modifier on PER + movement modifier on Stealth (perception §1d) ----
from kirby_combat.perception import range_modifier  # noqa: E402


def test_range_modifier_table():
    # 6E2 p40: no modifier ≤8m; −2 after 8m; −2 per range-doubling thereafter.
    assert range_modifier(0) == 0
    assert range_modifier(8) == 0
    assert range_modifier(9) == -2
    assert range_modifier(16) == -2
    assert range_modifier(17) == -4
    assert range_modifier(32) == -4
    assert range_modifier(33) == -6
    assert range_modifier(64) == -6
    assert range_modifier(65) == -8


class _StubSkill:
    def __init__(self, xmlid: str, roll_value: int):
        self.xmlid = xmlid
        self.roll_value = roll_value


class _StubHiderHero:
    """Target hero with a STEALTH skill (no senses/Invisibility). INT 10."""

    def __init__(self, stealth: int = 14, int_val: int = 10):
        self.name = "Hider"
        self.powers: list = []
        self.talents: list = []
        self.skills = [_StubSkill("STEALTH", stealth)]
        self._int = int_val

    def characteristic_value(self, xmlid: str) -> int:
        return {"INT": self._int}.get(xmlid.upper(), 0)


def _hider(stealth: int = 14) -> HeroCombatant:
    from kirby_combat.hero_view import HeroCombatState
    return HeroCombatant(
        id="target",
        hero=_StubHiderHero(stealth),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )


def test_stealth_contest_applies_range_modifier_to_per():
    obs = _hero_with_sense("NORMALSIGHT")   # INT 10 → PER 11
    tgt = _hider(stealth=14)
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=64.0)   # range mod −6
    p = perceive(obs, tgt, scene, target_hidden=True, roller=RandomRoller(seed=5))
    assert p.detail["range_modifier"] == -6
    assert p.detail["per"] == per_roll_target(obs) - 6


def test_movement_modifier_lowers_hider_stealth():
    obs = _hero_with_sense("NORMALSIGHT")
    tgt = _hider(stealth=14)
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=2.0)    # range mod 0
    p = perceive(obs, tgt, scene, target_hidden=True,
                 stealth_movement_modifier=-5, roller=RandomRoller(seed=5))
    # Noncombat movement (−5) makes the hider easier to spot → lower stealth target.
    assert p.detail["stealth"] == 14 - 5
    assert p.detail["range_modifier"] == 0


def test_extreme_range_per_drops_to_zero_cannot_perceive():
    obs = _hero_with_sense("NORMALSIGHT")   # PER 11
    tgt = _hider(stealth=14)
    scene = _two_combatant_scene_adjacent(obs, tgt, gap_m=300.0)  # range mod −12
    p = perceive(obs, tgt, scene, target_hidden=True, roller=RandomRoller(seed=5))
    # eff PER 11 − 12 = −1 ≤ 0 → too far to perceive even on a 3 (6E2 p9).
    assert p.targetable_physical is False


# --- Task E1: flash_groups(power) + perceive(observer_flashed_groups=) ---------
# Sense-Affecting Flash §1 (engine seam). A FLASH power encodes its Sense
# Group(s) identically to INVISIBILITY (option_id *GROUP token + assigned_adders
# GROUP tokens); a Flashed observer can't perceive via a flashed sense group.

from kirby_combat.perception import flash_groups


def test_flash_groups_reads_real_option_group():
    # Real shape: a FLASH power's primary group lives in power.option_id.
    class _P:
        xmlid = "FLASH"
        alias = "Flash"
        option_id = "SIGHTGROUP"
        assigned_adders: list = []
    assert flash_groups(_P()) == frozenset({SIGHT})


def test_flash_groups_defaults_to_sight_when_unparsed():
    # A present FLASH power with no parseable group → the Sight Group default.
    class _P:
        xmlid = "FLASH"
        alias = "Flash"
        adders: list = []
    assert flash_groups(_P()) == frozenset({SIGHT})


def test_flash_groups_reads_option_and_adder_groups():
    # Extra groups as GROUP-token adders, mirroring invisibility's shape.
    class _Adder:
        def __init__(self, xmlid):
            self.XMLID = xmlid
    class _P:
        xmlid = "FLASH"
        alias = "Flash"
        option_id = "SIGHTGROUP"
        assigned_adders = [_Adder("HEARINGGROUP")]
    assert flash_groups(_P()) == frozenset({SIGHT, HEARING})


def test_flash_groups_non_flash_power_is_empty():
    # A non-FLASH power covers no flashed groups.
    class _P:
        xmlid = "INVISIBILITY"
        alias = "Invisibility"
        option_id = "SIGHTGROUP"
        assigned_adders: list = []
    assert flash_groups(_P()) == frozenset()


def test_perceive_sight_flashed_observer_cannot_see():
    # A sight-only observer whose Sight group is flashed can't perceive the
    # target via sight → not physically targetable, kind "invisible".
    obs = _hero_with_sense("NORMALSIGHT")
    obs.id = "observer"
    tgt = _hero_with_sense("NORMALSIGHT")
    tgt.id = "target"
    scene = _two_combatant_scene(obs, tgt, wall=False)
    p = perceive(obs, tgt, scene, observer_flashed_groups=frozenset({SIGHT}))
    assert p.targetable_physical is False
    assert p.kind == "invisible"


def test_perceive_radar_observer_unaffected_by_sight_flash():
    # An observer with a non-Sight (Radar) sense + Sight flashed still perceives
    # via radar — the skip is group-scoped.
    obs = _hero_with_sense("RADAR")
    obs.id = "observer"
    tgt = _hero_with_sense("NORMALSIGHT")
    tgt.id = "target"
    scene = _two_combatant_scene(obs, tgt, wall=False)
    p = perceive(obs, tgt, scene, observer_flashed_groups=frozenset({SIGHT}))
    assert p.targetable_physical is True
    assert "radar" in p.via


# --- Task E2: darkness_groups(power) + darkness_personal_immunity + the gate ---
# Sense-Affecting Darkness §2. A darkness_zone Construct occludes a Sense Group
# on a crossing ray — it BEATS penetrative senses (Nightvision) and applies to
# mental senses too; the creating combatant with Personal Immunity sees through.

from kirby_combat.perception import (  # noqa: E402
    darkness_groups, darkness_personal_immunity, MENTAL,
)
from kirby_combat.scene.construct import Construct  # noqa: E402


def test_darkness_groups_reads_real_option_group():
    # A DARKNESS power encodes its Sense Group identically to FLASH/INVISIBILITY.
    class _P:
        xmlid = "DARKNESS"
        alias = "Darkness"
        option_id = "SIGHTGROUP"
        assigned_adders: list = []
    assert darkness_groups(_P()) == frozenset({SIGHT})


def test_darkness_groups_defaults_to_sight_when_unparsed():
    class _P:
        xmlid = "DARKNESS"
        alias = "Darkness"
        adders: list = []
    assert darkness_groups(_P()) == frozenset({SIGHT})


def test_darkness_groups_reads_option_and_adder_groups():
    class _Adder:
        def __init__(self, xmlid):
            self.XMLID = xmlid
    class _P:
        xmlid = "DARKNESS"
        alias = "Darkness"
        option_id = "MENTALGROUP"
        assigned_adders = [_Adder("HEARINGGROUP")]
    assert darkness_groups(_P()) == frozenset({MENTAL, HEARING})


def test_darkness_groups_non_darkness_power_is_empty():
    class _P:
        xmlid = "FLASH"
        alias = "Flash"
        option_id = "SIGHTGROUP"
        assigned_adders: list = []
    assert darkness_groups(_P()) == frozenset()


def test_darkness_personal_immunity_reads_adder():
    class _Adder:
        def __init__(self, xmlid, alias=""):
            self.XMLID = xmlid
            self.alias = alias
    class _P:
        xmlid = "DARKNESS"
        assigned_adders = [_Adder("PERSONALIMMUNITY", "Personal Immunity")]
    assert darkness_personal_immunity(_P()) is True

    class _P2:
        xmlid = "DARKNESS"
        assigned_adders = [_Adder("NOFRINGE", "No Fringe")]
    assert darkness_personal_immunity(_P2()) is False


def _darkness_zone(*, sense_group: str = "sight", creator_immune: bool = False,
                   source: str | None = None) -> Construct:
    # A box spanning x 8..12, y 0..10 — straddles the observer→target ray
    # (observer at x=0, target at x=20, both y=5). Elevation covers z=1.5.
    return Construct(
        obj_id="dz1", kind="darkness_zone",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_group=sense_group, creator_immune=creator_immune,
        source_combatant_id=source,
    )


def _scene_with_constructs(observer, target, constructs) -> Scene:
    observer.id, target.id = "observer", "target"
    return Scene(
        id="sdark", name="Darkness",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=list(constructs),
        combatant_positions={
            observer.id: Position(0, 5, 1.5),
            target.id: Position(20, 5, 1.5),
        },
    )


def test_darkness_zone_blocks_sight_on_crossing_ray():
    obs = _hero_with_sense("NORMALSIGHT")
    tgt = _hero_with_sense("NORMALSIGHT")
    scene = _scene_with_constructs(obs, tgt, [_darkness_zone(sense_group="sight")])
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is False
    assert p.kind in ("occluded", "invisible")


def test_darkness_beats_penetrative_sight_sense():
    # Nightvision/Spatial-Awareness-style penetrative SIGHT sense still blocked
    # by a Sight-Darkness — the gate runs BEFORE the penetrative short-circuit.
    from kirby_combat.hero_view import HeroCombatState
    obs = HeroCombatant(
        id="observer", hero=_PenetrativeObserverHero(),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=20, current_body=10, current_end=20),
    )
    spatial = [s for s in obs.senses() if s.xmlid == "SPATIALAWARENESS"]
    assert spatial and spatial[0].penetrative is True
    assert spatial[0].group == SIGHT
    tgt = _hero_with_sense("NORMALSIGHT")
    scene = _scene_with_constructs(obs, tgt, [_darkness_zone(sense_group="sight")])
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is False   # Darkness beats Nightvision


def test_non_sight_sense_perceives_through_sight_darkness():
    obs = _hero_with_sense("RADAR")         # RADIO group
    tgt = _hero_with_sense("NORMALSIGHT")
    scene = _scene_with_constructs(obs, tgt, [_darkness_zone(sense_group="sight")])
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True
    assert "radar" in p.via


def test_creator_with_immunity_sees_through_own_darkness():
    obs = _hero_with_sense("NORMALSIGHT")
    obs.id = "creator"
    tgt = _hero_with_sense("NORMALSIGHT")
    tgt.id = "target"
    scene = Scene(
        id="sdark2", name="Darkness",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=[_darkness_zone(sense_group="sight", creator_immune=True,
                                   source="creator")],
        combatant_positions={
            "creator": Position(0, 5, 1.5),
            "target": Position(20, 5, 1.5),
        },
    )
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is True    # creator + immunity sees through


def test_creator_without_immunity_is_blind_in_own_darkness():
    obs = _hero_with_sense("NORMALSIGHT")
    obs.id = "creator"
    tgt = _hero_with_sense("NORMALSIGHT")
    tgt.id = "target"
    scene = Scene(
        id="sdark3", name="Darkness",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=[_darkness_zone(sense_group="sight", creator_immune=False,
                                   source="creator")],
        combatant_positions={
            "creator": Position(0, 5, 1.5),
            "target": Position(20, 5, 1.5),
        },
    )
    p = perceive(obs, tgt, scene)
    assert p.targetable_physical is False   # creator without immunity is blind


def test_mental_darkness_blocks_mind_scan():
    # A Mental-Darkness on the ray blocks the Mind Scan sense itself. The
    # observer also has the always-present Normal Sight (which would otherwise
    # grant mental LOS), so we ALSO drop a Sight-Darkness on the ray to isolate
    # the mental channel → with Mind Scan blocked there is no mental targeting.
    obs = _hero_with_sense("MINDSCAN")      # MENTAL group, non-LOS sense
    tgt = _hero_with_sense("NORMALSIGHT")
    sight_dz = _darkness_zone(sense_group="sight")
    mental_dz = Construct(
        obj_id="dz_mental", kind="darkness_zone",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0), sense_group="mental",
    )
    scene = _scene_with_constructs(obs, tgt, [sight_dz, mental_dz])
    p = perceive(obs, tgt, scene)
    assert p.targetable_mental is False
    assert "mindscan" not in p.via


def test_darkness_gate_fails_open_without_scene_or_positions():
    obs = _hero_with_sense("NORMALSIGHT")
    tgt = _hero_with_sense("NORMALSIGHT")
    # scene-less call → no darkness gate, still perceives by sight via no-scene
    p = perceive(obs, tgt, None)
    assert p.targetable_physical is True


class _FixedRoller:
    """Rolls 3d6 summing to a fixed total (for disbelief contest tests)."""

    def __init__(self, total):
        self._total = total

    def roll_dice(self, n):
        base = self._total // n
        rem = self._total - base * n
        return [base + (1 if i < rem else 0) for i in range(n)]


def test_disbelieve_image_succeeds_when_roll_under_target():
    from kirby_combat.perception import disbelieve_image
    assert disbelieve_image(per_target=12, image_penalty=2, roller=_FixedRoller(6)) is True


def test_disbelieve_image_fails_when_roll_over_effective_target():
    from kirby_combat.perception import disbelieve_image
    assert disbelieve_image(per_target=11, image_penalty=4, roller=_FixedRoller(12)) is False


def test_disbelieve_image_penalty_lowers_effective_target():
    from kirby_combat.perception import disbelieve_image
    # roll of 9: penalty 0 (target 11) succeeds; penalty 4 (target 7) fails.
    assert disbelieve_image(per_target=11, image_penalty=0, roller=_FixedRoller(9)) is True
    assert disbelieve_image(per_target=11, image_penalty=4, roller=_FixedRoller(9)) is False

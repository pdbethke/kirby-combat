"""An ATTACK thrown at a man you cannot perceive — 6E2 p.127.

A2 wired 6E2 p.127 into the three maneuvers that had no engine rule at all
(Trip, Disarm, Sweep) and left the door it came in by open: a plain attack
--- the action nine fights out of ten consist of --- still rolled at full
OCV against full DCV in a Darkness field, and a Flashed gunman shot as
straight as a sighted one. `_cannot_perceive` and `sense_penalties`' table
were both already there; nothing on the attack path asked them.

THE TWO ROWS ARE DIFFERENT, and this is where the difference first
matters. 6E2 p.9 gives hand-to-hand and Ranged separate rows: HTH is half
OCV, Ranged is **zero** OCV. The maneuvers A2 wired are all hand-to-hand,
so its helper could hard-code the HTH row; an attack cannot, because the
same resolver fires a revolver and throws a punch.

And the payload says what it rolled against. `effective_ocv`,
`target_dcv` and `margin` were stamped onto a maneuver's event by A2 and
onto nothing else, so a blinded ATTACK and a badly rolled one were the
same row to any reader. They are stamped once now, in the recording path
both go through.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import FakeRoller

from kirby_combat.actions.flash import Flash
from kirby_combat.cv_modifiers import apply_cv_factor
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

OCV = 9
DCV = 5
DICE = 2

#: Two men one metre apart: no range penalty either way, so the only thing
#: that can move the OCV is the rule under test.
INSIDE = Position(10.0, 5.0, 1.5)
INSIDE_2 = Position(11.0, 5.0, 1.5)
OPEN = Position(30.0, 5.0, 1.5)
OPEN_2 = Position(31.0, 5.0, 1.5)


def _blast(source_id: str) -> AttackPower:
    """A ranged Blast — 6E2 p.9's Ranged row applies to it."""
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=DICE,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id, is_ranged=True,
    )


def _fist(source_id: str) -> AttackPower:
    """A hand-to-hand attack — 6E2 p.9's HTH row applies to it."""
    return AttackPower(
        xmlid="HANDTOHANDATTACK", name="Fist", damage_dice=DICE,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=0,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id, is_ranged=False, reach_m=2.0,
    )


def _man(id: str, *, side, power):
    return synthetic_combatant(
        id=id, name=id, ocv=OCV, dcv=DCV, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40,
        side=side, attacks=[power],
    )


def _darkness() -> Construct:
    """A Sight-Group Darkness field, x 8..12 by y 0..10 (6E1 p.188)."""
    return Construct(
        obj_id="dz1", kind="darkness_zone",
        polygon_xy=[(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)],
        elevation_range_m=(0.0, 3.0),
        sense_group="sight", creator_immune=False,
        source_combatant_id=None,
    )


def _scene(positions, constructs=()) -> Scene:
    return Scene(
        id="sblind", name="Blind", bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=list(constructs),
        combatant_positions=positions,
    )


def _fight(scene, *, power=_blast) -> CombatSession:
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=FakeRoller([]),
        combatants=[
            _man("brute", side=Side.named("villains"), power=power("brute-w")),
            _man("mark", side=Side.named("heroes"), power=power("mark-w")),
        ],
    ).start()


def _attack(power) -> LegalAction:
    return LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary="attack",
        _attack_view=power,
    )


def _resolve(session, to_hit: list[int], *, power):
    """`_attack_dice` draws to-hit 3d6, then damage, then Hit Location 3d6
    and the STUN Multiplier 1d6, in that order."""
    roller = FakeRoller([to_hit, [1] * DICE, [3, 3, 3], [1]])
    return resolve_chosen(
        session, session.combatants["brute"], _attack(power),
        template=TEMPLATE, roller=roller,
    )


def _payload(resolved):
    for event in reversed(resolved.session.event_log):
        payload = getattr(event, "result_payload", None)
        if isinstance(payload, dict) and "hit" in payload:
            return payload
    raise AssertionError("no resolution event on the log")


def _half(cv: int) -> int:
    """The engine's own halving (6E2 p.39), never a second copy of it."""
    return apply_cv_factor(cv, 0.5)


# ---------------------------------------------------------------------------
# The payload says what the roll was made against
# ---------------------------------------------------------------------------

def test_an_ordinary_attack_reports_what_it_rolled_against():
    """No blindness anywhere: the keys must still be there, carrying the
    unmodified numbers. Stamped in the recording path, so a maneuver and an
    attack get them from one place."""
    power = _blast("brute-w")
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    payload = _payload(_resolve(session, [4, 4, 4], power=power))

    assert payload["effective_ocv"] == OCV
    assert payload["target_dcv"] == DCV
    # 9 + 11 - 5 = 15, and a 12 lands with 3 to spare.
    assert payload["margin"] == 3
    assert payload["hit"] is True


# ---------------------------------------------------------------------------
# Hand-to-hand: half OCV, half DCV
# ---------------------------------------------------------------------------

def test_a_punch_in_the_dark_is_thrown_at_half_ocv():
    """Both men inside one Darkness field, swinging fists. 6E2 p.9's
    hand-to-hand row: half OCV for the man who cannot see, half DCV for the
    man who cannot see his attacker."""
    power = _fist("brute-w")
    session = _fight(
        _scene({"brute": INSIDE, "mark": INSIDE_2}, [_darkness()]), power=_fist,
    )
    payload = _payload(_resolve(session, [4, 4, 4], power=power))

    assert payload["effective_ocv"] == _half(OCV)
    assert payload["target_dcv"] == _half(DCV)


# ---------------------------------------------------------------------------
# At Range: OCV to ZERO
# ---------------------------------------------------------------------------

def test_a_shot_at_a_man_you_cannot_see_is_fired_at_zero_ocv():
    """6E2 p.9's Ranged row is harsher than the hand-to-hand one: OCV drops
    to ZERO, not to half. A helper that hard-codes the HTH row --- which is
    all a hand-to-hand maneuver ever needed --- gets this wrong by five."""
    power = _blast("brute-w")
    session = _fight(_scene({"brute": INSIDE, "mark": INSIDE_2}, [_darkness()]))
    payload = _payload(_resolve(session, [4, 4, 4], power=power))

    assert payload["effective_ocv"] == 0
    assert payload["target_dcv"] == _half(DCV)


def test_a_flashed_gunman_is_blind_and_his_target_is_not():
    """6E2 p.127 asks TWO questions of two different men. The Flashed
    attacker cannot perceive his target; the target sees him perfectly well
    and keeps every point of his DCV."""
    power = _blast("brute-w")
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    session, _ = Flash.apply(
        session, attacker_id="mark", target_id="brute",
        sense_group="sight", body_dealt=4, flash_defense=0,
    )
    payload = _payload(_resolve(session, [4, 4, 4], power=power))

    assert payload["effective_ocv"] == 0
    assert payload["target_dcv"] == DCV


def test_a_flashed_target_defends_at_half_dcv_against_a_man_who_sees_him():
    """The mirror: the penalty follows whoever is blind, and a full-sighted
    shooter loses nothing for it."""
    power = _blast("brute-w")
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    session, _ = Flash.apply(
        session, attacker_id="brute", target_id="mark",
        sense_group="sight", body_dealt=4, flash_defense=0,
    )
    payload = _payload(_resolve(session, [4, 4, 4], power=power))

    assert payload["effective_ocv"] == OCV
    assert payload["target_dcv"] == _half(DCV)

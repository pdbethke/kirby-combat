"""A maneuver thrown at a man you cannot perceive — 6E2 p.127.

"Inability To Sense An Opponent" (6E2 p.127, and the same rule with its
worked example on 6E2 p.9): a character who cannot perceive his opponent
with any Targeting Sense fights hand-to-hand at half OCV, and the man who
cannot perceive HIM defends at half DCV. Trip and Disarm are hand-to-hand
maneuvers, so the page's hand-to-hand row is the one that applies to them.

Both halves are asserted separately, because they are two different
questions asked of two different combatants: the attacker's OCV turns on
whether HE can see, the target's DCV on whether the TARGET can. A single
"blind" boolean cannot tell a flashed attacker swinging at a man who sees
him perfectly well from two men groping for each other in the dark.

Every maneuver also reports what it rolled against: `effective_ocv`,
`target_dcv` and `margin`, straight off the engine's own `ToHitResult`.
A to-hit that moved for a reason nobody recorded is indistinguishable
from a bad roll.
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
TRIP_OCV_MODIFIER = -1          # 6E2 p.67

#: `resolvers._attack_dice` draws to-hit 3d6, then damage (none, for a
#: maneuver that does none), then Hit Location 3d6 and the STUN Multiplier.
#: The Acrobatics save's 3d6 would come after them; nobody here has the
#: skill, so no save is ever rolled.
_LOCATION = [3, 3, 3]
_STUN_MULT = [1]

#: Positions inside and outside a Darkness field spanning x 8..12, y 0..10.
INSIDE = Position(10.0, 5.0, 1.5)
INSIDE_2 = Position(11.0, 6.0, 1.5)
OPEN = Position(30.0, 5.0, 1.5)
OPEN_2 = Position(31.0, 6.0, 1.5)


def _blast(source_id: str) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=source_id, is_ranged=True,
    )


def _man(id: str, *, side):
    return synthetic_combatant(
        id=id, name=id, ocv=OCV, dcv=DCV, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3,
        max_stun=40, max_body=12, max_end=40,
        side=side, attacks=[_blast(f"{id}-eb")],
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


def _fight(scene) -> CombatSession:
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=FakeRoller([]),
        combatants=[
            _man("brute", side=Side.named("villains")),
            _man("mark", side=Side.named("heroes")),
        ],
    ).start()


def _trip() -> LegalAction:
    return LegalAction(
        action_id="trip:mark", kind="trip", target_id="mark",
        power_xmlid=None, power_name=None, summary="trip",
        _attack_view=_blast("brute-eb"),
    )


def _roller(to_hit: list[int]) -> FakeRoller:
    return FakeRoller([to_hit, _LOCATION, _STUN_MULT])


def _resolve(session, to_hit: list[int]):
    return resolve_chosen(
        session, session.combatants["brute"], _trip(),
        template=TEMPLATE, roller=_roller(to_hit),
    )


def _half(cv: int) -> int:
    """The engine's own halving (6E2 p.39), never a second copy of it."""
    return apply_cv_factor(cv, 0.5)


# ---------------------------------------------------------------------------
# (a) The attacker cannot perceive the target
# ---------------------------------------------------------------------------

def test_a_trip_in_the_dark_is_thrown_at_half_ocv():
    """Two men inside one Darkness field: neither can see the other, so the
    attacker swings at half OCV and the target defends at half DCV."""
    session = _fight(_scene({"brute": INSIDE, "mark": INSIDE_2}, [_darkness()]))
    resolved = _resolve(session, [4, 4, 4])
    payload = resolved.session.event_log[-1].result_payload

    assert payload["effective_ocv"] == _half(OCV) + TRIP_OCV_MODIFIER
    assert payload["target_dcv"] == _half(DCV)
    # 5 - 1 = 4 OCV against 3 DCV: 4 + 11 - 3 = 12, and a 12 lands.
    assert payload["hit"] is True
    assert payload["margin"] == 0


def test_a_flashed_attacker_is_halved_and_the_man_who_sees_him_is_not():
    """6E2 p.127 asks TWO questions. A Flashed attacker cannot perceive his
    target, so his OCV is halved; the target can see him perfectly well and
    keeps his full DCV."""
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    session, _ = Flash.apply(
        session, attacker_id="mark", target_id="brute",
        sense_group="sight", body_dealt=4, flash_defense=0,
    )
    resolved = _resolve(session, [4, 4, 4])
    payload = resolved.session.event_log[-1].result_payload

    assert payload["effective_ocv"] == _half(OCV) + TRIP_OCV_MODIFIER
    assert payload["target_dcv"] == DCV


def test_a_flashed_target_defends_at_half_dcv_against_a_man_who_sees_him():
    """The mirror of the test above: the penalty follows whoever is blind."""
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    session, _ = Flash.apply(
        session, attacker_id="brute", target_id="mark",
        sense_group="sight", body_dealt=4, flash_defense=0,
    )
    resolved = _resolve(session, [4, 4, 4])
    payload = resolved.session.event_log[-1].result_payload

    assert payload["effective_ocv"] == OCV + TRIP_OCV_MODIFIER
    assert payload["target_dcv"] == _half(DCV)


# ---------------------------------------------------------------------------
# (b) A sighted maneuver reports what it rolled against
# ---------------------------------------------------------------------------

def test_a_sighted_trip_carries_the_margin_and_the_cvs():
    """No penalty, and the payload agrees with the engine's ToHitResult."""
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    resolved = _resolve(session, [4, 4, 4])
    payload = resolved.session.event_log[-1].result_payload
    to_hit = resolved.result.to_hit

    assert payload["effective_ocv"] == OCV + TRIP_OCV_MODIFIER == to_hit.effective_ocv
    assert payload["target_dcv"] == DCV == to_hit.effective_dcv
    assert payload["margin"] == to_hit.margin
    assert payload["margin"] == to_hit.target_number - to_hit.roll


def test_disarm_reports_the_same_three_facts():
    """The report belongs to the maneuver path, not to Trip -- Disarm is
    -2 OCV (6E2 p.65) and carries the same keys."""
    session = _fight(_scene({"brute": OPEN, "mark": OPEN_2}))
    disarm = LegalAction(
        action_id="disarm:mark", kind="disarm", target_id="mark",
        power_xmlid=None, power_name=None, summary="disarm",
        _attack_view=_blast("brute-eb"),
    )
    resolved = resolve_chosen(
        session, session.combatants["brute"], disarm,
        template=TEMPLATE, roller=_roller([4, 4, 4]),
    )
    payload = resolved.session.event_log[-1].result_payload

    assert payload["effective_ocv"] == OCV - 2
    assert payload["target_dcv"] == DCV
    assert payload["margin"] == resolved.result.to_hit.margin


# ---------------------------------------------------------------------------
# (c) No scene
# ---------------------------------------------------------------------------

def test_no_scene_means_nothing_blocks_a_sense():
    """A session with no Scene has no geometry, so nothing occludes a sense
    and no penalty applies -- the same numbers a sighted fight gets."""
    session = _fight(None)
    resolved = _resolve(session, [4, 4, 4])
    payload = resolved.session.event_log[-1].result_payload

    assert payload["effective_ocv"] == OCV + TRIP_OCV_MODIFIER
    assert payload["target_dcv"] == DCV
    assert payload["margin"] == resolved.result.to_hit.margin

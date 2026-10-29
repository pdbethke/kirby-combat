"""Every martial maneuver the menu offers resolves through the engine.

THE DEFECT THIS GUARDS (prod, 2026-10-26). Enumeration offered a
``maneuver`` action for each of a character's own attack maneuvers with
``power_xmlid="MANEUVER"``. The ``maneuver`` resolver looked that up in the
static 16-row ``MARTIAL_MANEUVERS`` table, found nothing, and raised
``UnresolvableAction`` --- a 500 on kirby-api's ``/run`` the first time a
martial artist chose one. And for a table id it only DECLARED: the
``modifiers_for_pending_attack`` the declaration fed had no reader at all,
so even a "resolved" maneuver changed nothing. The old api driver that rolled
them was deleted in the harness refactor.

So every test here takes the offer from the real ``enumerate_actions`` (fed
the way ``run_phase`` feeds it) for a real corpus martial artist, resolves it
through ``resolve_chosen`` or ``run_phase(on_unresolvable="raise")``, and
asserts the rule it is supposed to carry:

- the maneuver's OCV on its own Attack Roll and its DCV until the actor's
  next Phase (6E2 p.68: the -2 DCV of a missed Grab "remains ... until his
  next Phase"), read through the one CV door every attack takes;
- its damage: STR + the maneuver's DCs + Extra DCs as Normal Damage (6E2
  p.92, p.94, p.101), Killing Damage at 3 DC per d6 with STR added as to an
  HKA (6E2 p.93, p.99; 6E1 p.244), NND at 1/2d6 per DC without STR (6E2
  p.94, p.99, p.101);
- its effect class: Target Falls (6E2 p.94), You Fall (Sacrifice Throw,
  p.94), Grab and its holding STR (Martial Grab, p.94; Choke Hold, p.86/93),
  Disarm (Martial Disarm, p.94).

A maneuver whose effect the engine cannot build faithfully is NOT OFFERED:
an offered-but-unresolvable kind is the defect, never the price of honesty.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from kirby_dice import RandomRoller

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from kirby_combat.actions import recording
from kirby_combat.actions.grab import Grab
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.models import AttackInput, DiceValues
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import SegmentAdvanced, make_author_engine
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.tables import segments_for_spd
from kirby_combat.template import CombatTemplate

from tests.corpus import require_authored, require_authored_doc

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _AlwaysLow(RandomRoller):
    """Every die shows 1: every Attack Roll is a 3 and hits (6E2 p.37)."""

    def roll_dice(self, n):
        return [1] * n


class _AlwaysHigh(RandomRoller):
    """Every die shows 6: every Attack Roll is an 18 and misses (6E2 p.37)."""

    def roll_dice(self, n):
        return [6] * n


def _maneuver(id_: str, display: str, effect: str, *, ocv: str, dcv: str,
              dc: int, add_str: bool, damage_type: int = 0) -> dict:
    """One bought maneuver in the build-doc shape HD's own files produce.

    The values are Main6E.hdt's definitions of the 6E2 Martial Maneuvers
    Table (6E2 p.93) --- the template is what HD writes into every file
    that buys one, so this is the corpus shape, not an invention.
    """
    return {
        "id": id_, "xmlid": "MANEUVER", "base_cost": 4.0, "alias": display,
        "maneuver": True, "category": "Hand To Hand", "display": display,
        "ocv": ocv, "dcv": dcv, "dc": dc, "phase": "1/2", "effect": effect,
        "add_str": add_str, "maneuver_active_cost": 0,
        "damage_type": damage_type, "max_str": 0, "str_multiplier": 1,
        "use_weapon": False,
    }


#: The 6E2 p.93 table, as Main6E.hdt defines each row.
BUILT = [
    _maneuver("m-strike", "Martial Strike", "[NORMALDC] Strike",
              ocv="+0", dcv="+2", dc=2, add_str=True),
    _maneuver("m-offensive", "Offensive Strike", "[NORMALDC] Strike",
              ocv="-2", dcv="+1", dc=4, add_str=True),
    _maneuver("m-killing", "Killing Strike", "[KILLINGDC]",
              ocv="-2", dcv="+0", dc=2, add_str=True),
    _maneuver("m-nerve", "Nerve Strike", "[NNDDC]",
              ocv="-1", dcv="+1", dc=4, add_str=False),
    _maneuver("m-legsweep", "Legsweep", "[NORMALDC] Strike, Target Falls",
              ocv="+2", dcv="-1", dc=1, add_str=True),
    _maneuver("m-throw", "Martial Throw", "[NORMALDC] +v/10, Target Falls",
              ocv="+0", dcv="+1", dc=0, add_str=True),
    _maneuver("m-sacrifice", "Sacrifice Throw",
              "[NORMALDC] Strike; You Fall, Target Falls",
              ocv="+2", dcv="+1", dc=0, add_str=True),
    _maneuver("m-grab", "Martial Grab", "Grab Two Limbs, [STRDC] for holding on",
              ocv="-1", dcv="-1", dc=2, add_str=True),
    _maneuver("m-choke", "Choke Hold", "Grab One Limb; [NNDDC]",
              ocv="-2", dcv="+0", dc=4, add_str=False),
    _maneuver("m-disarm", "Martial Disarm", "Disarm; [STRDC] to Disarm",
              ocv="-1", dcv="+1", dc=2, add_str=True),
]

#: Maneuvers HD can build whose effect this engine cannot carry faithfully.
#: Each must stay OFF the menu --- see `kirby_combat/actions/maneuver_effects.py`.
#: (FMove, Must Follow, Crush, Takeaway, Shove and Martial Flash are built
#: now: `tests/loop/test_maneuvers_complete.py`.)
NOT_BUILT = [
    # Bind: a HERO System Martial Arts element with no 6E core mechanic.
    _maneuver("x-bind", "Weapon Bind", "Bind, [STRDC]",
              ocv="+1", dcv="+0", dc=2, add_str=True),
    # Disable: 6E2 p.111-113's optional Impairing/Disabling over Hit Locations.
    _maneuver("x-break", "Joint Break", "Grab One Limb; [KILLINGDC], Disable",
              ocv="-1", dcv="-2", dc=4, add_str=True),
    # HD's own output for a custom "Strike" with damage type NONE is the
    # bare word: it does no damage (kirby-cost Maneuver.does_damage).
    _maneuver("x-custom", "Custom Maneuver", "Strike",
              ocv="+1", dcv="-2", dc=4, add_str=True),
    # A Martial Flash bought against no Sense Group (no INPUT).
    _maneuver("x-flash", "Martial Flash", "[FLASHDC]",
              ocv="-1", dcv="-1", dc=4, add_str=False),
    # A hand-written STR figure HD never costed.
    _maneuver("x-cobra", "Cobra Grab", "Grab Two Limbs, 60 STR for holding on",
              ocv="-1", dcv="-1", dc=2, add_str=True),
]

#: The maneuvers whose offer names a weapon in the target's hand.
ARMED = {"Martial Disarm"}

#: One Extra Damage Class (6E2 p.94): +1 DC to every maneuver, +5 STR to a
#: maneuver that grants STR for a limited purpose.
EXTRA_DC = {
    "id": "x-dc", "xmlid": "EXTRADC", "levels": 1, "base_cost": 0.0,
    "level_cost": 4.0, "level_value": 1.0, "alias": "+1 HTH Damage Class(es)",
}

ACTOR_AT = Position(10.0, 10.0, 0.0)
MARK_AT = Position(11.0, 10.0, 0.0)


def _ravel() -> HeroCombatant:
    """The corpus martial artist, exactly as imported."""
    return replace(HeroCombatant.from_build(require_authored("Ravel"), id="ravel"),
                   side=Side.named("a"))


def _student() -> HeroCombatant:
    """Ravel, having also studied the whole 6E2 table and the HD rows this
    engine refuses, plus one Extra DC --- built through the cost engine."""
    from kirby_cost.io.build_json import build_from_json

    doc = copy.deepcopy(require_authored_doc("Ravel"))
    doc["martial_arts"] = (list(doc["martial_arts"]) + BUILT + NOT_BUILT
                           + [EXTRA_DC])
    return replace(HeroCombatant.from_build(build_from_json(doc), id="ravel"),
                   side=Side.named("a"))


def _mark():
    return synthetic_combatant(
        id="mark", name="mark", ocv=6, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=15, ego=10, str_=15, con=18, pre=10, rec=6,
        pd=4, ed=4, rpd=0, red=0, md=0,
        max_stun=60, max_body=15, max_end=40, side=Side.named("b"),
    )


def _armed_mark():
    """Bokor, as imported: his Mojo Hand is an Obvious Accessible Focus
    (6E1 p.379), the thing a Disarm takes."""
    return replace(HeroCombatant.from_build(require_authored("Bokor"), id="mark"),
                   side=Side.named("b"))


def _session_for(name: str, actor=None) -> CombatSession:
    """A mat on which ``name`` has something to act on."""
    actor = actor if actor is not None else _student()
    return _session(actor, mark=_armed_mark() if name in ARMED else None)


def _session(actor, mark=None) -> CombatSession:
    mark = mark if mark is not None else _mark()
    scene = Scene(
        id="mat", name="Mat", bounds=SceneBounds(0, 0, 0, 40, 40, 10),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={actor.id: ACTOR_AT, "mark": MARK_AT},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
        combatants=[actor, mark],
    ).start()


def _menu(session, actor_id: str = "ravel"):
    """The menu `run_phase` builds --- its own door, so every fact it folds
    from the fight (who holds what weapon, who is holding whom) is fed."""
    from kirby_combat.loop.run import _situation_for

    return _situation_for(session, actor_id).menu


def _maneuvers(session) -> dict[str, object]:
    return {a.power_name: a for a in _menu(session) if a.kind == "maneuver"}


def _row(session) -> dict:
    """The last action row's payload (a Disarm writes a `WeaponMoved` after it)."""
    return next(e.result_payload for e in reversed(session.event_log)
                if e.kind == "ActionResolved")


def _resolve(session, offer, roller):
    return resolve_chosen(session, session.combatants["ravel"], offer,
                          template=TEMPLATE, roller=roller)


@pytest.fixture
def rolled(monkeypatch):
    """Every `AttackInput` that reaches the pure resolver, in order."""
    seen: list = []
    original = recording.resolve_attack

    def spy(attack, template):
        seen.append(attack)
        return original(attack, template)

    monkeypatch.setattr(recording, "resolve_attack", spy)
    return seen


def _attack_on(session, defender_id: str) -> AttackInput:
    """What the CV door makes of a plain punch thrown at `defender_id`."""
    attacker_id = next(c for c in session.combatants if c != defender_id)
    attacker = session.combatants[attacker_id]
    return recording._fold_session_cvs(session, AttackInput(
        attacker=attacker, target=session.combatants[defender_id],
        power=attacker.str_strike_view(), distance_m=1.0, aim=None,
        dice=DiceValues(),
    ))


def _to_his_next_phase(session, combatant_id: str) -> CombatSession:
    """Advance the log into this man's next Phase Segment."""
    spd = int(session.combatants[combatant_id].combat_stats().spd)
    here = session.timeline.segment
    phases = sorted(segments_for_spd(spd))
    nxt = next((s for s in phases if s > here), phases[0])
    import uuid
    from datetime import datetime, timezone

    return apply_event(session, SegmentAdvanced(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=here, to_segment=nxt, to_turn=session.timeline.turn,
    ))


# ---------------------------------------------------------------------------
# The corpus martial artist, as imported.
# ---------------------------------------------------------------------------

def test_ravels_joint_lock_is_offered_and_resolves_through_run_phase():
    """Ravel's Joint Lock/Throw (Grab One Limb; [NNDDC]; Target Falls,
    DC 2) through the loop's own step door, refusing on anything it
    cannot execute. This is the exact shape that 500'd on /run."""
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import run_phase

    session = _session(_ravel())
    offers = _maneuvers(session)
    assert set(offers) == {"Joint Lock/Throw"}, (
        "Grappling Block is a Block (Abort) and is not an offensive offer")
    joint_lock = offers["Joint Lock/Throw"]

    class _Picks:
        def choose(self, situation):
            assert joint_lock.action_id in {a.action_id for a in situation.menu}
            return joint_lock.action_id

    encounter = Encounter(id="e", turn=session.timeline.turn,
                          segment=session.timeline.segment, sessions=[session])
    # Step until it is Ravel's Phase; anyone else's Phase is spent Dodging.
    for _ in range(24):
        result = run_phase(encounter, _PicksFor("ravel", _Picks()),
                           roller=_AlwaysLow(seed=1), on_unresolvable="raise")
        encounter = result.encounter
        if result.actor_id == "ravel":
            break
    else:
        pytest.fail("Ravel never got a Phase")
    after = encounter.sessions[0]

    # Grab One Limb: he is held, by her (6E2 p.67 / p.86).
    assert Grab.is_grabbed(after, "mark") == (True, "ravel")
    # Target Falls (6E2 p.94).
    assert PRONE in statuses_for(after, "mark")
    # [NNDDC] at DC 2 is 1d6 NND (6E2 p.99: each DC of an NND is 1/2d6),
    # STUN only, and it ignores his PD 4 (he has no rigid armour).
    payload = next(
        e.result_payload for e in reversed(after.event_log)
        if e.kind == "ActionResolved"
        and e.result_payload.get("maneuver_id") == joint_lock._maneuver_view.maneuver_id
    )
    assert payload["hit"] is True
    assert payload["stun_dealt"] == 1 and payload["body_dealt"] == 0


class _PicksFor:
    """Picks for one actor; everyone else takes a Dodge."""

    def __init__(self, actor_id, chooser):
        self.actor_id, self.chooser = actor_id, chooser

    def choose(self, situation):
        if situation.actor.id == self.actor_id:
            return self.chooser.choose(situation)
        dodge = [a for a in situation.menu if a.kind in ("dodge", "recover")]
        return (dodge or situation.menu)[0].action_id


# ---------------------------------------------------------------------------
# What is offered, and what is not.
# ---------------------------------------------------------------------------

def test_every_6e2_maneuver_is_offered_and_every_unbuildable_one_is_not():
    offered = set(_maneuvers(_session(_student(), mark=_armed_mark())))
    assert offered >= {m["display"] for m in BUILT}
    refused = {m["display"] for m in NOT_BUILT} & offered
    assert not refused, f"offered but not buildable: {sorted(refused)}"


@pytest.mark.parametrize("name", [m["display"] for m in BUILT])
@pytest.mark.parametrize("dice", [_AlwaysLow, _AlwaysHigh], ids=["hit", "miss"])
def test_every_offered_maneuver_resolves(name, dice):
    session = _session_for(name)
    offer = _maneuvers(session)[name]
    resolved = _resolve(session, offer, dice(seed=1))
    assert resolved.events, f"{name} recorded nothing"
    payload = _row(resolved.session)
    assert payload["maneuver_id"] == offer._maneuver_view.maneuver_id
    assert payload["hit"] is (dice is _AlwaysLow)


def test_an_offer_without_its_maneuver_refuses():
    """The offer carries the maneuver it names; without it the resolver
    would have to guess which of the character's maneuvers was meant."""
    session = _session(_student())
    offer = replace(_maneuvers(session)["Martial Strike"], _maneuver_view=None)
    with pytest.raises(UnresolvableAction, match="maneuver"):
        _resolve(session, offer, _AlwaysLow(seed=1))


# ---------------------------------------------------------------------------
# OCV on the roll, DCV until his next Phase.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, ocv", [
    ("Martial Strike", 0), ("Offensive Strike", -2), ("Killing Strike", -2),
    ("Nerve Strike", -1), ("Legsweep", 2), ("Martial Grab", -1),
    ("Choke Hold", -2), ("Martial Disarm", -1),
])
def test_the_maneuvers_ocv_reaches_its_attack_roll(name, ocv, rolled):
    session = _session_for(name)
    _resolve(session, _maneuvers(session)[name], _AlwaysLow(seed=1))
    (attack,) = rolled
    # The door may add its own conditions; none apply on an open mat, so
    # what remains is exactly the maneuver's OCV.
    assert attack.ocv_modifier == ocv


@pytest.mark.parametrize("name, dcv", [
    ("Martial Strike", 2), ("Offensive Strike", 1), ("Legsweep", -1),
    ("Nerve Strike", 1), ("Martial Disarm", 1),
])
def test_the_maneuvers_dcv_lasts_until_his_next_phase(name, dcv):
    """6E2 p.68: a maneuver's DCV modifier stays with him "until his next
    Phase". Read through the same door every attack on him takes."""
    session = _session_for(name)
    assert _attack_on(session, "ravel").dcv_modifier == 0
    after = _resolve(session, _maneuvers(session)[name], _AlwaysHigh(seed=1)).session
    assert _attack_on(after, "ravel").dcv_modifier == dcv
    later = _to_his_next_phase(after, "ravel")
    assert _attack_on(later, "ravel").dcv_modifier == 0


def test_a_grab_that_lands_replaces_its_dcv_penalty():
    """6E2 p.68: "If the Grab succeeds, the Grabber suffers the 1/2 DCV
    penalty described below - this replaces the -2 DCV penalty"; a missed
    Grab leaves him at the maneuver's DCV until his next Phase."""
    session = _session(_student())
    missed = _resolve(session, _maneuvers(session)["Martial Grab"],
                      _AlwaysHigh(seed=1)).session
    assert _attack_on(missed, "ravel").dcv_modifier == -1
    landed = _resolve(session, _maneuvers(session)["Martial Grab"],
                      _AlwaysLow(seed=1)).session
    assert landed.event_log[-1].result_payload.get("maneuver_dcv") is None


# ---------------------------------------------------------------------------
# Damage.
# ---------------------------------------------------------------------------
# Ravel: STR 10 (2 DC), plus the one Extra DC every maneuver here receives.

@pytest.mark.parametrize("name, dice, half, plus_one, kind, nnd", [
    # STR 2d6 + 2 DC + 1 Extra DC (6E2 p.93 "STR +2d6 Strike"; p.94 Extra DC).
    ("Martial Strike", 5, False, False, "normal", False),
    ("Offensive Strike", 7, False, False, "normal", False),
    # Legsweep "STR +1d6" (6E2 p.93): 2 + 1 + 1.
    ("Legsweep", 4, False, False, "normal", False),
    # Martial Throw from a standstill: STR, +v/10 from no velocity adds
    # nothing (6E2 p.101), + the Extra DC.
    ("Martial Throw", 3, False, False, "normal", False),
    # Killing Strike: 2 DC + 1 Extra DC + STR 10's 2 DC = 5 DC = 1 1/2d6
    # HKA (6E2 p.99 Damage Class Table; STR added as to an HKA, p.93).
    ("Killing Strike", 1, True, False, "killing", False),
    # Nerve Strike: 4 DC + 1 Extra = 5 DC of NND = 2 1/2d6, no STR
    # (6E2 p.99: an NND DC is 1/2d6; p.101: NND strikes add no damage).
    ("Nerve Strike", 2, True, False, "normal", True),
    ("Choke Hold", 2, True, False, "normal", True),
])
def test_the_maneuvers_damage(name, dice, half, plus_one, kind, nnd, rolled):
    session = _session(_student())
    _resolve(session, _maneuvers(session)[name], _AlwaysLow(seed=1))
    (attack,) = rolled
    p = attack.power
    assert (p.damage_dice, p.half_die, p.plus_one, p.damage_type, p.avad) == (
        dice, half, plus_one, kind, nnd)
    # A half die is ROLLED: one more d6 than the full dice.
    assert len(attack.dice.damage) == dice + (1 if half else 0)


def test_an_nnd_maneuver_does_stun_only_through_no_defense():
    session = _session(_student())
    resolved = _resolve(session, _maneuvers(session)["Nerve Strike"],
                        _AlwaysLow(seed=1))
    payload = resolved.session.event_log[-1].result_payload
    # Every point of STUN rolled gets through: his PD 4 is not the defense
    # (6E2 p.94), and an NND does no BODY (6E1 p.328).
    assert payload["stun_dealt"] == resolved.result.damage.stun > 0
    assert payload["body_dealt"] == 0


def test_a_martial_maneuver_costs_only_the_end_of_its_str():
    """6E2 p.93: "They do not cost END to use, though the character has to
    pay END for any STR used with them.\""""
    session = _session(_student())
    # What the attack costs, whether or not this campaign counts END
    # (RAW_SUPERHEROIC does not: `recording._tracks_endurance`).
    nerve = _resolve(session, _maneuvers(session)["Nerve Strike"], _AlwaysLow(seed=1))
    assert nerve.result.end_spent == 0
    strike = _resolve(session, _maneuvers(session)["Martial Strike"], _AlwaysLow(seed=1))
    # STR 10 is 1 END (6E1 p.132).
    assert strike.result.end_spent == 1


# ---------------------------------------------------------------------------
# Effects.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Legsweep", "Martial Throw", "Sacrifice Throw"])
def test_target_falls_when_it_lands(name):
    session = _session(_student())
    landed = _resolve(session, _maneuvers(session)[name], _AlwaysLow(seed=1)).session
    assert PRONE in statuses_for(landed, "mark")
    missed = _resolve(session, _maneuvers(session)[name], _AlwaysHigh(seed=1)).session
    assert PRONE not in statuses_for(missed, "mark")


def test_a_sacrifice_throw_puts_the_thrower_down_too():
    """6E2 p.94: "the Thrower himself ends up prone where he was standing"."""
    session = _session(_student())
    landed = _resolve(session, _maneuvers(session)["Sacrifice Throw"],
                      _AlwaysLow(seed=1)).session
    assert PRONE in statuses_for(landed, "ravel")
    legsweep = _resolve(session, _maneuvers(session)["Legsweep"],
                        _AlwaysLow(seed=1)).session
    assert PRONE not in statuses_for(legsweep, "ravel")


@pytest.mark.parametrize("name", ["Martial Grab", "Choke Hold"])
def test_a_grab_maneuver_takes_hold(name):
    session = _session(_student())
    landed = _resolve(session, _maneuvers(session)[name], _AlwaysLow(seed=1)).session
    assert Grab.is_grabbed(landed, "mark") == (True, "ravel")
    missed = _resolve(session, _maneuvers(session)[name], _AlwaysHigh(seed=1)).session
    assert Grab.is_grabbed(missed, "mark") == (False, None)


def test_martial_grabs_holding_str_resists_the_escape():
    """6E2 p.94, Martial Grab: the STR bonus "only helps the character hold
    the target". [STRDC] at DC 2 + 1 Extra DC is +15 STR (p.94: an Extra DC
    is +5 STR to a maneuver that grants STR for a limited purpose)."""
    session = _session(_student())
    held = _resolve(session, _maneuvers(session)["Martial Grab"],
                    _AlwaysLow(seed=1)).session
    escape = next(a for a in _menu(held, "mark") if a.action_id == "escape:grab:full")
    after = resolve_chosen(held, held.combatants["mark"], escape,
                           template=TEMPLATE, roller=_AlwaysLow(seed=1)).session
    payload = next(e.result_payload for e in reversed(after.event_log)
                   if e.kind == "ActionResolved")
    assert payload["grabber_str"] == 10 + 15


def test_martial_disarm_records_its_contest_str():
    session = _session_for("Martial Disarm")
    after = _resolve(session, _maneuvers(session)["Martial Disarm"],
                     _AlwaysLow(seed=1)).session
    payload = _row(after)
    assert payload["disarm_str"] == 10 + 15
    assert payload["stun_dealt"] == 0 and payload["body_dealt"] == 0

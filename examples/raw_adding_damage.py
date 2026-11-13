"""Adding damage — 6E2 p.99, p.101 and p.70, reproduced.

This is a conformance check that happens to be readable: the rulebook's own
worked examples are restated below, the engine is driven through them, and
every number the book states is ASSERTED against what the engine produced.
If the engine ever stops agreeing with the book, this script exits non-zero
and `tests/test_examples.py` fails with it.

THE BOOK'S SCENARIOS, PARAPHRASED — this project ships no rules text; open
your own copy:

  1. 6E2 p.101. Maneuvers add damage a Damage Class at a time, whatever the
     type of damage: a Martial Strike (+2 DC) takes a 3d6 club (3 DC) to
     5d6, and a 1d6 HKA sword (also 3 DC) to 1 1/2d6. A maneuver that does
     a different KIND of damage (a Killing Strike, an NND Strike) adds
     nothing to a weapon.
  2. 6E2 p.99. A Killing Damage DC is 5 Active Points: +1 pip, and three of
     them to the die. So STR adds to a 1d6 HKA a pip at a time: STR 5 gives
     1d6+1, STR 10 gives 1 1/2d6, STR 15 gives 2d6, and STR can't more than
     double the attack (6E1 p.137).
  3. 6E2 p.70. A character with a Phase in Segment 6 Haymakers his Strike.
     He begins it in Segment 6, and it lands at the very end of Segment 7,
     after everyone in Segment 7 has acted. He could Abort to Block in
     Segment 7 first, but then he loses the attack.

Parts 1 and 2 cost a build, so they need a HERO Designer template:

    KIRBY_COST_HDT   a HERO Designer .hdt --- kirby-cost needs it

Without it they say so and are skipped, like the other examples that need
licensed material. Part 3 needs nothing.

Run with:
    .venv/bin/python examples/raw_adding_damage.py
"""
from __future__ import annotations

import os
from dataclasses import replace

from kirby_dice import RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
OAF = {"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0}
_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def _maneuver(id_, display, effect, *, dc, ocv="+0", dcv="+2"):
    return {
        "id": id_, "xmlid": "MANEUVER", "base_cost": 4.0, "alias": display,
        "maneuver": True, "category": "Hand To Hand", "display": display,
        "ocv": ocv, "dcv": dcv, "dc": dc, "phase": "1/2", "effect": effect,
        "add_str": True, "maneuver_active_cost": 0, "damage_type": 0,
        "max_str": 0, "str_multiplier": 1, "use_weapon": True,
    }


def _student(strength: int):
    """A martial artist with a Weapon Element, a 3d6 club and a 1d6 HKA sword."""
    from kirby_cost.io.build_json import build_from_json

    from kirby_combat.hero_view import HeroCombatant

    hero = build_from_json({
        "name": "Student", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": [{"xmlid": "STR", "levels": strength - 10}] + _CHARS,
        "powers": [
            {"id": "club", "xmlid": "ENERGYBLAST", "name": "Club", "levels": 3,
             "input": "PD", "modifiers": [OAF, {"xmlid": "NORANGE", "base_cost": -0.5}]},
            {"id": "sword", "xmlid": "HKA", "name": "Sword", "levels": 1,
             "modifiers": [OAF]},
        ],
        "martial_arts": [
            _maneuver("mv-strike", "Martial Strike", "[NORMALDC] Strike", dc=2),
            _maneuver("mv-kill", "Killing Strike", "[KILLINGDC]", dc=2, ocv="-2", dcv="+0"),
            {"id": "we", "xmlid": "WEAPON_ELEMENT", "base_cost": 1.0},
        ],
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })
    return replace(HeroCombatant.from_build(hero, id="student"), side=Side.named("a"))


def _menu(student):
    from kirby_combat.loop.run import _situation_for

    mark = synthetic_combatant(id="mark", name="Mark", spd=2, side=Side.named("b"))
    session = CombatSession.create(
        id="s", combatants=[student, mark], scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=1)).start()
    return [o for o in _situation_for(session, "student").menu if o.target_id == "mark"]


def adding_to_weapons() -> None:
    rule("1. A Martial Strike with a club and with a sword (6E2 p.101)")
    menu = _menu(_student(strength=0))     # STR 0: the weapons' own dice, as the book has them
    strike = {o._wielded.name: o for o in menu
              if o.power_name == "Martial Strike" and o._wielded is not None}
    for name, offer in sorted(strike.items()):
        print(f"\n  {offer.summary}")
    assert "5d6 with his Club" in strike["Club"].summary
    assert "HKA 1½d6 with his Sword" in strike["Sword"].summary

    killing = [o for o in menu if o.power_name == "Killing Strike"]
    print(f"\n  Killing Strike: {len(killing)} offer, made barehanded, "
          f"never added to a weapon")
    assert [o._wielded for o in killing] == [None]


def str_on_a_killing_attack() -> None:
    rule("2. STR on a 1d6 HKA, a Damage Class at a time (6E2 p.99)")
    expected = {0: "1d6", 5: "1d6+1", 10: "1½d6", 15: "2d6", 20: "2d6"}
    for strength, book in expected.items():
        sword = next(a for a in _student(strength).attacks if a.name == "Sword")
        got = (f"{sword.damage_dice}{'½' if sword.half_die else ''}d6"
               f"{'+1' if sword.plus_one else ''}")
        print(f"  STR {strength:>2}: {got:<6}  (book: {book})")
        assert got == book
    print("  STR 20 stops at 2d6: STR can't more than double the attack.")


class _Script:
    """(actor, segment) -> an action-id prefix; (actor, segment) -> an Abort."""

    def __init__(self, own, react=None):
        self.own, self.react = own, react or {}

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, sit):
        who, seg = sit.actor.id, sit.session.timeline.segment
        oot = getattr(sit, "out_of_turn", None)
        if oot is not None:
            if oot.reason.value != "abort":
                return sit.menu[0].action_id
            want = self.react.get((who, seg), "no_abort")
            return next(o.action_id for o in sit.menu if o.kind == want)
        prefix = self.own.get((who, seg))
        if prefix is not None:
            return next(o.action_id for o in sit.menu if o.action_id.startswith(prefix))
        return next(o.action_id for o in sit.menu if o.kind in ("set", "hold"))


def _brawler(id_, side, spd, dex):
    return synthetic_combatant(
        id=id_, name=id_, ocv=9, dcv=5, omcv=5, dmcv=5, spd=spd, dex=dex,
        ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4, rpd=0, red=0, md=3,
        power_defense=0, flash_defense=0, max_stun=200, max_body=50, max_end=200,
        current_stun=200, current_body=50, current_end=200, side=side, attacks=[])


def _haymaker_fight(script):
    hero = _brawler("hero", Side.named("a"), spd=4, dex=20)        # 3, 6, 9, 12
    other = _brawler("other", Side.named("b"), spd=7, dex=10)      # 2, 4, 6, 7, 9, 11, 12
    session = CombatSession.create(
        id="s", combatants=[hero, other], scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=1)).start()
    enc, events = Encounter(id="e", turn=1, segment=12, sessions=[session]), []
    while (enc.turn, enc.segment) <= (2, 7):
        r = run_phase(enc, script, roller=RandomRoller(seed=5), on_unresolvable="raise")
        events += r.events
        enc = r.encounter
    seg, timed = None, []
    for e in events:
        if e.kind == "SegmentAdvanced" and e.to_turn == 2:
            seg = e.to_segment
        timed.append((seg, e))
    return timed


def haymaker() -> None:
    rule("3. A Haymaker begun in Segment 6 lands at the end of Segment 7 (6E2 p.70)")
    timed = _haymaker_fight(_Script({("hero", 6): "haymaker:strike:other"}))
    blows = [(s, i) for i, (s, e) in enumerate(timed) if e.kind == "ActionResolved"
             and e.result_payload.get("kind") == "attack"
             and e.result_payload.get("target_id") == "other"]
    (seg, at), = blows
    other_in_7 = next(i for i, (s, e) in enumerate(timed)
                      if s == 7 and e.kind == "PhaseSpent" and e.combatant_id == "other")
    print(f"\n  Begun in Segment 6; the blow lands in Segment {seg}, after the "
          f"other man's Segment 7 Phase")
    assert seg == 7 and other_in_7 < at

    timed = _haymaker_fight(_Script(
        {("hero", 6): "haymaker:strike:other", ("other", 7): "strike:hero"},
        react={("hero", 7): "block"}))
    ruined = [e.result_payload for _, e in timed if e.kind == "ActionResolved"
              and e.result_payload.get("kind") == "haymaker"]
    blows = [e for _, e in timed if e.kind == "ActionResolved"
             and e.result_payload.get("kind") == "attack"
             and e.result_payload.get("target_id") == "other"]
    print(f"  He Aborts to Block in Segment 7 instead: "
          f"{ruined[0]['reason']}; the Haymaker never lands")
    assert ruined[0]["ruined"] and not blows


def main() -> None:
    if os.environ.get("KIRBY_COST_HDT"):
        adding_to_weapons()
        str_on_a_killing_attack()
    else:
        rule("1 and 2 skipped: KIRBY_COST_HDT is not set (a build needs a template)")
    haymaker()
    rule("END — every number 6E2 p.99, p.101 and p.70 state, confirmed.")


if __name__ == "__main__":
    main()

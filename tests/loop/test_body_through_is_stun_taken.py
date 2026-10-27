"""BODY that gets through costs STUN, whatever the defenses did to the STUN.

6E2 p.105: "Regardless of whether an attack does Normal Damage or Killing
Damage, a character automatically takes 1 STUN for every 1 point of BODY
damage that gets through his defenses." The book's own example is Ogre, PD
40 with 5 of it Resistant, shot for 10 BODY / 30 STUN: "he would normally
take 5 BODY, 0 STUN. Because he took BODY damage, he takes a minimum of 1
STUN per point of BODY taken, so he takes 5 STUN regardless of his
defenses."

Found in kirby-app's 0.22.0 demo recording: Drago's Armor Piercing RKA put
8, 6, 6 and 6 BODY into GORGON (ED 35, no resistant ED) and every hit
reported `stun_dealt: 0` until the last, so GORGON went to -1 BODY having
lost one point of STUN. The payload and `VitalsChanged` agreed with each
other; both were short of the rule.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_dice import RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.loop.run import run_phase
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate


class Ones:
    """Every die a one: the to-hit is a 3 (always hits, 6E2 p.37), each
    killing die is 1 BODY and the STUN Multiplier's half die is 1."""

    def roll_dice(self, n: int) -> list[int]:
        return [1] * n


def _rka(source_id: str) -> AttackPower:
    return AttackPower(
        xmlid="RKA", name="pistol", damage_dice=4, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id=source_id,
    )


def _man(id: str, side: str, *, dex: int, pd: int, rpd: int):
    return synthetic_combatant(
        id=id, name=id, ocv=9, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=pd, ed=pd, rpd=rpd, red=rpd, md=3, power_defense=0,
        flash_defense=0, max_stun=60, max_body=20, max_end=40,
        current_stun=60, current_body=20, current_end=40,
        side=Side.named(side), attacks=[_rka(f"{id}-rka")],
    )


class Shoots:
    def choose(self, situation) -> str:
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        for offer in situation.menu:
            if offer.kind == "attack":
                return offer.action_id
        raise AssertionError([a.action_id for a in situation.menu])


def _shot(*, pd: int, rpd: int):
    session = CombatSession.create(
        id="s", combatants=[_man("drago", "a", dex=30, pd=4, rpd=0),
                            _man("gorgon", "b", dex=10, pd=pd, rpd=rpd)],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    result = run_phase(enc, Shoots(), roller=Ones(), on_unresolvable="raise")
    assert result.actor_id == "drago" and result.kind == "attack"
    vitals = [e for e in result.events if e.kind == "VitalsChanged"
              and e.combatant_id == "gorgon"]
    resolved = [e for e in result.events if e.kind == "ActionResolved"]
    return result, vitals, resolved[-1].result_payload


def test_body_through_no_resistant_defense_costs_that_much_stun():
    """4 BODY x1 = 4 STUN against PD 35: defenses stop all the STUN and
    none of the BODY. He takes 4 BODY, so he takes 4 STUN."""
    result, vitals, payload = _shot(pd=35, rpd=0)
    assert payload["body_dealt"] == 4
    assert payload["stun_dealt"] == 4, "6E2 p.105: 1 STUN per BODY taken"
    assert [(e.stun, e.body) for e in vitals] == [(-4, -4)]
    assert result.session.combatants["gorgon"].current_stun == 56


def test_the_floor_never_lowers_stun_that_got_through_anyway():
    """No defense at all: 4 STUN, 4 BODY, exactly the dice."""
    _, _, payload = _shot(pd=0, rpd=0)
    assert (payload["stun_dealt"], payload["body_dealt"]) == (4, 4)


def test_no_body_through_is_no_floor():
    """Resistant 10 stops every BODY, so nothing is owed (6E2 p.105 is
    BODY "that gets through")."""
    _, vitals, payload = _shot(pd=35, rpd=10)
    assert (payload["stun_dealt"], payload["body_dealt"]) == (0, 0)
    assert vitals == []

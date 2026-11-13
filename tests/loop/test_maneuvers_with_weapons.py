"""A martial maneuver made with a weapon adds its DCs to the weapon's.

6E2 p.94: a style used with weapons (Fencing) can't be used barehanded; any
other style needs a Weapon Element to be used with a weapon, and stays usable
barehanded. HD records "used with a weapon" per maneuver (USEWEAPON) and the
Element as a WEAPON_ELEMENT purchase; PeterB's ruling (2026-11-13) is to
trust HD's flag as stated.

6E2 p.101: "Maneuvers add damage at the standard rate, +1 DC for each +1 DC
from the Maneuver, regardless of the type of damage done": a Martial Strike
(+2 DC) takes a 3d6 club to 5d6 and a 1d6 HKA sword to 1 1/2d6. A maneuver
that adds no dice (a Killing Strike, an NND Strike) adds nothing to a weapon.

Before this, a maneuver HD marked "used with a weapon" was offered and
resolved barehanded: 56 corpus maneuvers on 16 characters.

Every test drives enumeration (`legal_actions`, through `_situation_for`) and
`resolve_chosen`: the offer the menu makes and the blow the resolver lands.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_dice import RandomRoller

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import _situation_for
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]

OAF = {"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0}


class _AlwaysLow(RandomRoller):
    """Every die shows 1: every Attack Roll is a 3 and hits (6E2 p.37)."""

    def roll_dice(self, n, sides=6):
        return [1] * n


def _maneuver(id_, display, effect, *, dc, use_weapon, ocv="+0", dcv="+2"):
    return {
        "id": id_, "xmlid": "MANEUVER", "base_cost": 4.0, "alias": display,
        "maneuver": True, "category": "Hand To Hand", "display": display,
        "ocv": ocv, "dcv": dcv, "dc": dc, "phase": "1/2", "effect": effect,
        "add_str": True, "maneuver_active_cost": 0, "damage_type": 0,
        "max_str": 0, "str_multiplier": 1, "use_weapon": use_weapon,
    }


def _strike(use_weapon):
    return _maneuver("mv-strike", "Martial Strike", "[NORMALDC] Strike",
                     dc=2, use_weapon=use_weapon)


def _killing(use_weapon):
    return _maneuver("mv-kill", "Killing Strike", "[KILLINGDC]",
                     dc=2, use_weapon=use_weapon, ocv="-2", dcv="+0")


#: A 3d6 club (Normal Damage, hand-to-hand) and a 1d6 HKA sword, both OAF.
CLUB = {"id": "club", "xmlid": "ENERGYBLAST", "name": "Club", "levels": 3,
        "input": "PD", "modifiers": [OAF, {"xmlid": "NORANGE", "base_cost": -0.5}]}
SWORD = {"id": "sword", "xmlid": "HKA", "name": "Sword", "levels": 1,
         "modifiers": [OAF]}


def _fighter(*, strength, weapons, maneuvers, element=False):
    from kirby_cost.io.build_json import build_from_json

    arts = list(maneuvers)
    if element:
        arts.append({"id": "we", "xmlid": "WEAPON_ELEMENT", "base_cost": 1.0})
    hero = build_from_json({
        "name": "Student", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": [{"xmlid": "STR", "levels": strength - 10}] + _CHARS,
        "powers": list(weapons), "martial_arts": arts,
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })
    return replace(HeroCombatant.from_build(hero, id="student"), side=Side.named("a"))


def _session(student):
    mark = synthetic_combatant(id="mark", name="Mark", spd=2, dex=5,
                               side=Side.named("b"))
    return CombatSession.create(
        id="s", combatants=[student, mark], scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=1)).start()


def _menu(session):
    return _situation_for(session, "student").menu


def _forms(session, name):
    """{weapon name or None: offer} for the named maneuver against Mark."""
    return {
        (o._wielded.name if o._wielded is not None else None): o
        for o in _menu(session)
        if o.kind == "maneuver" and o.power_name == name and o.target_id == "mark"
    }


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


# ── 6E2 p.101's worked example ──────────────────────────────────────────────

def test_a_martial_strike_takes_the_club_to_5d6_and_the_sword_to_one_and_a_half():
    student = _fighter(strength=0, weapons=[CLUB, SWORD],
                       maneuvers=[_strike(True)], element=True)
    forms = _forms(_session(student), "Martial Strike")
    assert set(forms) == {None, "Club", "Sword"}
    assert "5d6 with his Club" in forms["Club"].summary
    assert "HKA 1½d6 with his Sword" in forms["Sword"].summary


def test_the_blow_lands_with_the_weapon_s_dice_and_type():
    student = _fighter(strength=0, weapons=[SWORD], maneuvers=[_strike(True)],
                       element=True)
    session = _session(student)
    offer = _forms(session, "Martial Strike")["Sword"]
    resolved = resolve_chosen(session, session.combatants["student"], offer,
                              template=TEMPLATE, roller=_AlwaysLow(seed=1))
    row = [e for e in resolved.events if e.kind == "ActionResolved"][-1].result_payload
    assert row["hit"] is True
    assert row["damage_type"] == "killing"
    assert row["power_name"] == "Martial Strike with Sword"
    assert row["wielded_name"] == "Sword"
    # Every die shows 1: 1 1/2d6 is a die and a half die, 2 BODY. The bare
    # sword's 1d6 would be 1.
    assert row["body_dealt"] == 2


def test_str_counts_on_the_weapon_then_the_maneuver_adds():
    """STR 15 on a 1d6 HKA is 2d6 (6 DC, the Doubling Rule's cap); the
    Martial Strike's +2 DC makes it 8 DC: 2 1/2d6."""
    student = _fighter(strength=15, weapons=[SWORD], maneuvers=[_strike(True)],
                       element=True)
    forms = _forms(_session(student), "Martial Strike")
    assert "HKA 2½d6 with his Sword" in forms["Sword"].summary


# ── who may use it with what (6E2 p.94) ─────────────────────────────────────

def test_without_a_weapon_element_it_is_a_weapon_style_and_not_barehanded():
    student = _fighter(strength=0, weapons=[CLUB], maneuvers=[_strike(True)])
    assert set(_forms(_session(student), "Martial Strike")) == {"Club"}


def test_a_weapon_style_with_no_weapon_in_hand_offers_nothing():
    student = _fighter(strength=0, weapons=[], maneuvers=[_strike(True)])
    assert _forms(_session(student), "Martial Strike") == {}


def test_a_maneuver_not_marked_for_weapons_stays_barehanded():
    student = _fighter(strength=0, weapons=[CLUB], maneuvers=[_strike(False)],
                       element=True)
    assert set(_forms(_session(student), "Martial Strike")) == {None}


def test_a_killing_strike_adds_nothing_to_a_weapon():
    """6E2 p.101: "Its function isn't to add, but to differentiate." It is
    offered as it stands, never as a weapon form."""
    student = _fighter(strength=0, weapons=[SWORD], maneuvers=[_killing(True)],
                       element=True)
    assert set(_forms(_session(student), "Killing Strike")) == {None}


def test_a_weapon_out_of_his_hand_is_not_offered():
    from kirby_combat import weapons as W

    student = _fighter(strength=0, weapons=[CLUB], maneuvers=[_strike(True)],
                       element=True)
    session = _session(student)
    (club,) = W.accessible_foci(student)
    session = W.move_weapon(session, club, by_id="mark", cause=W.DISARMED,
                            holder_id="mark", position=None)
    assert set(_forms(session, "Martial Strike")) == {None}

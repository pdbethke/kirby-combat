"""Gunmen with real Accessible Foci, for the grip and wound tests.

Built through `build_from_json` like `tests/loop/test_maneuvers_with_weapons.py`,
so the weapons are found by `weapons.accessible_foci` exactly as a corpus
character's are. Peter's own construction, no licensed names.
"""
from __future__ import annotations

from dataclasses import replace

from kirby_dice import RandomRoller

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant

OAF = {"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0}
TWO_HANDS = {"xmlid": "REQUIREDHANDS", "option_id": "TWO", "base_cost": -0.5}
_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


def gun(id_, name, *, two_handed=False):
    mods = [OAF] + ([TWO_HANDS] if two_handed else [])
    return {"id": id_, "xmlid": "RKA", "name": name, "levels": 2,
            "input": "PD", "modifiers": mods}


def gunman(id_, *guns, side="a"):
    from kirby_cost.io.build_json import build_from_json

    hero = build_from_json({
        "name": id_, "template": "builtIn.Heroic6E.hdt", "base_points": 175,
        "disad_points": 50, "experience": 0, "characteristics": _CHARS,
        "powers": list(guns), "skills": [], "perks": [], "talents": [],
        "martial_arts": [], "disadvantages": [], "equipment": [],
    })
    return replace(HeroCombatant.from_build(hero, id=id_), side=Side.named(side))


def session_of(*men, template):
    mark = synthetic_combatant(id="mark", name="Mark", spd=2, dex=5,
                               side=Side.named("b"))
    return CombatSession.create(
        id="s", combatants=[*men, mark], scene=None,
        template=template,
        dice_roller=RandomRoller(seed=1)).start()


def weapon_id(man, name):
    """His weapon's id, as `weapons.accessible_foci` finds it."""
    from kirby_combat.weapons import accessible_foci

    return next(w.weapon_id for w in accessible_foci(man) if w.name == name)

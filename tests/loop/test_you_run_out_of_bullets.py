"""Six shots, and then you are holding an empty revolver.

`HeroCombatState.used_charges` has existed for a long time --- declared,
documented as "Power xmlid -> number of charges spent in this combat",
and serialized in BOTH directions. Nothing has ever written it and
nothing has ever read it, so nobody in any fight this engine has run has
ever needed to reload.

PeterB asked the question that found it: "are you recording ammo?
charges".

The counts were in the builds the whole time. HSEG's Colt Peacemaker is
`<MODIFIER XMLID="CHARGES" OPTIONID="SIX">`; the Winchester '73 has
sixteen; Doc Holliday's coach gun has ONE, and he has been firing it four
times a fight.

6E1 p.334: "Each slot of a Charges power lets the character use the power
the defined number of times per day." Charges are uses.

COUNTED BY THE POWER'S OWN ID, not its xmlid. Doc carries a Shotgun and a
Colt Peacemaker and BOTH are RKA --- counting by type would empty one gun
by firing the other. That is the same "identity is an id" lesson
`_power_action_id` already refuses to compromise on.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.charges import charges_on, spent_charges
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_engine,
)


class _Mod:
    def __init__(self, xmlid, option_id="", alias_for_vector=""):
        self.xmlid = xmlid
        self.option_id = option_id
        self.alias_for_vector = alias_for_vector


class _Gun:
    def __init__(self, *mods):
        self.assigned_modifiers = list(mods)


class _Log:
    def __init__(self, events=()):
        self.event_log = list(events)


def _base() -> dict:
    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _fired(who: str, source_id: str) -> list:
    d = ActionDeclared(**_base(), combatant_id=who, action_type="attack",
                       targets=["x"])
    r = ActionResolved(**_base(), declaration_event_id=d.id,
                       result_payload={"kind": "attack", "hit": True,
                                       "power_source_id": source_id})
    return [d, r]


# ---- reading the count off the build ----

def test_a_revolver_holds_six():
    assert charges_on(_Gun(_Mod("CHARGES", "SIX", "6"))) == 6


def test_a_coach_gun_holds_one():
    assert charges_on(_Gun(_Mod("CHARGES", "ONE", "1"))) == 1


def test_a_winchester_holds_sixteen():
    assert charges_on(_Gun(_Mod("CHARGES", "SIXTEEN", "16"))) == 16


def test_a_power_with_no_charges_is_not_limited():
    """None, not zero --- "unlimited" and "empty" must never be the same
    answer, or every innate power stops working."""
    assert charges_on(_Gun(_Mod("FOCUS"))) is None


# ---- counting what has been fired ----

def test_nothing_fired_is_nothing_spent():
    assert spent_charges(_Log(), "wyatt") == {}


def test_each_shot_counts():
    log = _Log(_fired("wyatt", "colt-1") + _fired("wyatt", "colt-1"))
    assert spent_charges(log, "wyatt") == {"colt-1": 2}


def test_two_guns_of_the_same_type_are_counted_apart():
    """Doc's Shotgun and his Colt are BOTH RKA. Counting by xmlid would
    empty one by firing the other."""
    log = _Log(_fired("doc", "shotgun-1") + _fired("doc", "colt-9")
               + _fired("doc", "colt-9"))
    assert spent_charges(log, "doc") == {"shotgun-1": 1, "colt-9": 2}


def test_somebody_elses_shots_are_not_yours():
    log = _Log(_fired("wyatt", "colt-1"))
    assert spent_charges(log, "doc") == {}


# ---- and an empty gun is not on the menu ----

def _armed_with(charges, spent):
    """A fighter whose one weapon has `charges` and has fired `spent`."""
    from conftest import blast, fighter
    from kirby_combat.side import Side

    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    gun = _Gun(_Mod("CHARGES", "", str(charges)))
    gun.id = actor.attacks[0].source_id
    actor.hero.powers = [gun]
    return actor, {gun.id: spent}


def _menu(actor, spent):
    from conftest import fighter
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.side import Side

    return enumerate_actions(
        actor, [fighter("frank", side=Side.named("cow"))],
        spent_charges=spent,
    )


def test_a_loaded_gun_is_offered():
    actor, spent = _armed_with(charges=6, spent=2)
    assert [a for a in _menu(actor, spent) if a.kind == "attack"]


def test_an_empty_gun_is_not():
    """Six shots fired from a six-shooter. The GUN's offer has to go, or
    he keeps firing an empty revolver for ever --- which is what he did."""
    actor, spent = _armed_with(charges=6, spent=6)
    gun_id = actor.attacks[0].source_id
    assert not [a for a in _menu(actor, spent)
                if a.kind == "attack" and gun_id in a.action_id]


def test_but_he_can_still_punch():
    """An empty revolver leaves a man with his fists, not with nothing.
    The bare-STR fallback has to come AFTER the ammunition filter, which
    is why the filter sits where it does."""
    actor, spent = _armed_with(charges=6, spent=6)
    assert [a for a in _menu(actor, spent) if a.kind == "attack"], (
        "he should still be able to hit somebody"
    )


def test_a_coach_gun_is_empty_after_one():
    actor, spent = _armed_with(charges=1, spent=1)
    gun_id = actor.attacks[0].source_id
    assert not [a for a in _menu(actor, spent)
                if a.kind == "attack" and gun_id in a.action_id]


def test_an_innate_power_never_runs_dry():
    """No CHARGES modifier means unlimited, and must not read as empty."""
    from conftest import fighter
    from kirby_combat.side import Side

    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    actor.hero.powers = [_Gun(_Mod("FOCUS"))]
    assert [a for a in _menu(actor, {}) if a.kind == "attack"]

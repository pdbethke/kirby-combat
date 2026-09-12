"""A man on his own cannot Coordinate an attack.

6E2 p.46 states the requirements, and the first is flat:

    "A character cannot 'Coordinate' with himself."

    "To Coordinate attacks, the characters must attack on the same DEX
     on the same Phase (the attacks are considered to occur
     simultaneously). Faster characters may have to Hold their Actions
     to wait for comrades who have lower DEXs."

`coordinate` was offered 1,355 times across the western benchmarks and
taken zero times. Measured on the corral: **12 of 187 offers went to a
man with no standing ally at all** --- the last Cowboy alive, invited to
coordinate with the dead.

The offer was gated on `alive_enemies and allow_coordinate`, and
`allow_coordinate` is a parameter defaulting True that NOTHING in this
package ever sets. So the only condition it ever really tested was that
somebody was left to shoot at.

WHAT THIS DOES NOT FIX, and cannot from here. The same-DEX/same-Phase
requirement needs to know which Segment it is and who else has a Phase
in it; `enumerate_actions` takes no `segment` argument and has no phase
table. That gate belongs to the driver, which already "resolves roll +
join + execution semantics" per the offer's own comment. Recorded here
so the remaining half is a known hole rather than an assumption.
"""
from __future__ import annotations

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat.enumeration import enumerate_actions


def _coordinates(allies) -> list[str]:
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4,
                     assigned_modifiers=[_StubPower(xmlid="BEAM")])
    actor = _combatant(id="frank", powers=[gun])
    enemy = _combatant(id="wyatt", powers=[gun])
    return [a.action_id for a in
            enumerate_actions(actor, [enemy], allies=allies,
                              distances={"wyatt": 30.0})
            if a.kind == "coordinate"]


def _ally(id: str, *, down: bool = False):
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4)
    overrides = {"current_stun": 0} if down else None
    return _combatant(id=id, powers=[gun], state_overrides=overrides)


def test_the_last_man_standing_is_offered_no_coordination():
    assert _coordinates([]) == []


def test_coordinating_with_the_dead_is_not_offered():
    """`run.py` passes fallen allies deliberately --- a chooser is told who
    it has lost. That list must not read as a partner."""
    assert _coordinates([_ally("tom", down=True)]) == []


def test_a_standing_ally_restores_the_offer():
    assert _coordinates([_ally("billy")]) != []


def test_one_standing_ally_among_the_fallen_is_enough():
    assert _coordinates([_ally("tom", down=True), _ally("billy")]) != []

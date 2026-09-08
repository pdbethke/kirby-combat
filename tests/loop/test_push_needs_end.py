"""Pushing needs something to spend --- 6E2 p.135.

Found at the O.K. Corral, by a model reading the Brief and answering
"I will use a PUSH Shotgun attack to maximize damage while I have the END
reserves". Doc Holliday's coach gun is HSEG equipment: RKA with CHARGES,
FOCUS and REAL WEAPON. It costs him no END at all, so there is nothing to
Push it with, and the menu offered it anyway.

6E2 p.135 is explicit about which abilities can be Pushed: generally only
Powers that cost END. Powers that never cost END, that are bought to 0
END, or that have CHARGES cannot be --- though a Power bought to 1/2 END
still can, which is why the gate cannot simply be "has a Reduced
Endurance modifier".

The engine already answers this exactly, and to Java parity:
`GenericObject.uses_end` in kirby-cost computes it from the modifiers
(CHARGES forces False, COSTSEND forces True, REDUCEDEND follows its
option -- HALFEND keeps END, ZERO does not), reading the parent List's
modifiers as well as the power's own. So enumeration ASKS it rather than
re-deriving a second, disagreeing copy of the same rule.
"""
from __future__ import annotations

from conftest import blast, fighter          # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.side import Side


class _SourcePower:
    """A loaded power object, as far as enumeration is concerned: an id to
    be found by, and the engine's own answer about END."""

    def __init__(self, id: str, uses_end: bool) -> None:
        self.id = id
        self.uses_end = uses_end
        self.assigned_modifiers: list = []


def _gunman(uses_end: bool):
    actor = fighter("gunman", side=Side.named("law"))
    actor.hero.powers = [_SourcePower("gunman-eb", uses_end=uses_end)]
    return actor


def _pushes(actor):
    enemy = fighter("mark", side=Side.named("outlaw"))
    return [a for a in enumerate_actions(actor, [enemy]) if a.kind == "push"]


def test_a_weapon_on_charges_is_not_offered_a_push():
    """Doc Holliday's shotgun. Nothing to spend, so nothing to Push."""
    assert not _pushes(_gunman(uses_end=False))


def test_a_power_that_costs_end_is_still_offered_a_push():
    """Guards the guard: the gate must not close on everything."""
    assert _pushes(_gunman(uses_end=True))

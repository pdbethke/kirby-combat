"""Block is a HTH maneuver, and a gunfight is not HTH.

6E2 p.59 is explicit twice over:

    "Blocks only affect Ranged attacks with the GM's permission,
     according to special rules (see below)."

and, listing what Block does cover:

    "A character can normally Block any HTH Combat attack, including
     Disarms, Chokes, Grabs/Grab Bys, Move Bys/Throughs, sword blows,
     most No Range attacks..."

THE GATE ALREADY EXISTED AND THIS OFFER DID NOT USE IT. `_melee_gate`
decides reach for melee attacks, Move By, Move Through, Coordinate and
Spreading. Block was offered for every living enemy regardless of
distance, so a man forty metres from a rifle was invited to block it ---
1,388 times across the two western benchmarks, taken zero times.

The comment above the offer site reads: "Block reaches `mark_aborting`
too, so it wears the same gate. Gating one defence and not the others is
how this class of defect survived its first fix." It wore the ABORT
gate. It never wore the REACH one.

WHAT THIS DELIBERATELY DOES NOT DO. Missile Deflection is the "special
rules" the page defers to, and this engine has no concept of it --- no
occurrence anywhere in the package, and no corral character buys it. So
the gate is reach alone. If Deflection is ever built, this is the offer
that has to learn about it, and that is recorded here rather than left
for someone to rediscover.
"""
from __future__ import annotations

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat.enumeration import enumerate_actions


def _blocks(*, apart_m: float) -> list[str]:
    """Block offers when the enemy stands `apart_m` away.

    `distances` is a PARAMETER of `enumerate_actions`, not something it
    derives from a Scene -- the loop computes it and passes it in. A
    first draft of this built an elaborate Scene and passed no distances,
    so `_melee_gate` took its scene-less branch and offered `strike`,
    `grab` and `trip` at forty metres too. That would have tested
    nothing.
    """
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4,
                     assigned_modifiers=[_StubPower(xmlid="BEAM")])
    actor = _combatant(id="frank", powers=[gun])
    enemy = _combatant(id="wyatt", powers=[gun])

    return [a.action_id for a in
            enumerate_actions(actor, [enemy], distances={"wyatt": apart_m})
            if a.kind == "block"]


def test_you_cannot_block_a_man_forty_metres_away():
    assert _blocks(apart_m=40.0) == []


def test_you_can_still_block_the_man_in_front_of_you():
    """The maneuver is not removed --- a gunfight at arm's length is a
    fistfight, and Wyatt Earp pistol-whipped Tom McLaury in this one."""
    assert _blocks(apart_m=1.0) != []

"""The no-op shim is gone, and the flat type is named for what it is.

models.py carried `combat_stats()` returning self and `state` returning self,
so the resolution layer could read either shape without dispatch. Its own
comment said "This goes away in step 6 when LegacyCombatant is deleted."

Deleting the TYPE turned out to be wrong -- Vehicle and ObjectCombatant
subclass it and are built from flat values, with BODY/DEF from a material
table rather than a build. A stone wall has no LoadedHero to wrap. So the type
stays, renamed for what it actually is, and only the shim goes.
"""
from __future__ import annotations

import inspect

from kirby_combat.models import StatBlockCombatant


def test_the_flat_type_is_named_for_what_it_is():
    assert StatBlockCombatant.__name__ == "StatBlockCombatant"


def test_the_flat_type_satisfies_the_ancestor_contract():
    """It must be a CombatParticipant and it must be constructible.

    The plan first said to DELETE combat_stats()/state here as "the no-op
    shim". That was wrong: the ABC declares both abstract, and a flat
    dataclass holding current_stun directly implements them by returning
    itself. Deleting them makes this class abstract and every construction
    below raises TypeError.
    """
    from kirby_combat.participant import CombatParticipant

    assert issubclass(StatBlockCombatant, CombatParticipant)


def test_the_stale_shim_comment_is_gone():
    """The comment said "This goes away in step 6 when LegacyCombatant is
    deleted." Step 6 is this task, and the methods are staying -- so the
    comment now describes a plan that was abandoned for a measured reason."""
    src = inspect.getsource(StatBlockCombatant)
    assert "combatant-redesign step 4" not in src
    assert "LegacyCombatant" not in src


def test_it_still_carries_its_own_stats():
    """It is a stat block. Removing the shim must not remove the stats."""
    c = StatBlockCombatant(
        id="x", name="X", ocv=8, dcv=8, omcv=3, dmcv=3, spd=4, dex=18, ego=10,
        str_=15, con=20, pre=15, rec=8, pd=8, ed=8, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0, max_stun=40, max_body=12,
        max_end=40, current_stun=40, current_body=12, current_end=40,
        attacks=[], defenses=[], csls=[],
    )
    assert c.ocv == 8 and c.current_stun == 40

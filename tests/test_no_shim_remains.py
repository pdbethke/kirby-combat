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
import re

import pytest

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


def test_the_stale_names_are_gone_from_hero_view_too():
    """Scoping the check to `inspect.getsource(StatBlockCombatant)` was too
    narrow to do its job. hero_view.py kept its own copy of the abandoned
    plan -- "combatant-redesign step 6", "the flat Combatant", "When
    LegacyCombatant deletes" -- and referred to `models.Combatant`, a name
    that no longer exists. The class-scoped grep above cannot see another
    module, so it passed the whole time. Check the file."""
    import kirby_combat.hero_view

    src = inspect.getsource(kirby_combat.hero_view)
    assert "LegacyCombatant" not in src
    assert "combatant-redesign step 6" not in src
    assert "models.Combatant" not in src
    # `Combatant` must only ever appear as the tail of a real type name
    # (HeroCombatant / StatBlockCombatant / ObjectCombatant). `\b` does not
    # match inside those, so any hit here is a bare, dead reference.
    bare = [
        src[max(0, m.start() - 60):m.end() + 20]
        for m in re.finditer(r"\bCombatant\b", src)
    ]
    assert not bare, bare


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


def test_state_returns_the_same_object_not_a_copy():
    """`StatBlockCombatant.state` returning `self` is an identity
    DISCRIMINATOR, not just a convenience.

    `actions/movement/base.py::_decrement_end` dispatches on
    `combatant.state is not combatant` to decide whether END lives on a
    separate state object. If `state` ever returned a copy, every stat block
    would take the HeroCombatant branch, which does
    `dataclasses.replace(combatant, state=...)`. Measured 2026-08-25:
    StatBlockCombatant has no `state` FIELD, so that raises
    `TypeError: StatBlockCombatant.__init__() got an unexpected keyword
    argument 'state'`. Identity, not equality, is what keeps it correct.
    """
    from dataclasses import replace

    c = StatBlockCombatant(
        id="x", name="X", ocv=8, dcv=8, omcv=3, dmcv=3, spd=4, dex=18, ego=10,
        str_=15, con=20, pre=15, rec=8, pd=8, ed=8, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0, max_stun=40, max_body=12,
        max_end=40, current_stun=40, current_body=12, current_end=40,
    )
    assert c.state is c
    assert c.combat_stats() is c

    # The failure the identity check prevents, demonstrated.
    with pytest.raises(TypeError):
        replace(c, state=object())


def test_decrement_end_takes_the_flat_branch_for_a_stat_block():
    """The discriminator, exercised end-to-end at its one real call site."""
    from kirby_combat.actions.movement.base import _decrement_end

    c = StatBlockCombatant(
        id="x", name="X", ocv=8, dcv=8, omcv=3, dmcv=3, spd=4, dex=18, ego=10,
        str_=15, con=20, pre=15, rec=8, pd=8, ed=8, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0, max_stun=40, max_body=12,
        max_end=40, current_stun=40, current_body=12, current_end=40,
    )
    assert _decrement_end(c, 6).current_end == 34

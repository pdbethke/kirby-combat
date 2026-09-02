"""A slot fights with the modifiers its pool carries.

``_has_modifier`` / ``_modifier_levels`` used to be a flat loop over a power's
own ``assigned_modifiers``. Everything reading them — ARMORPIERCING,
PENETRATING, HARDENED, IMPENETRABLE, DOESBODY — therefore under-reported for
any power inside a Power Framework, because HD puts the Advantage on the POOL
and prints it on each slot.

Nothing in the existing suite covers a pooled slot, which is why the flat scan
survived: the delegation to ``kirby_cost.model.modifiers`` moved no
expectation. These fail against the flat scan and pass against the engine walk.
"""
from __future__ import annotations

from kirby_combat.hero_view import _has_modifier, _modifier_levels


class _Mod:
    def __init__(self, xmlid, levels=0, private=False):
        self.xmlid, self.levels, self.private = xmlid, levels, private


class _Power:
    def __init__(self, xmlid="BLAST", mods=(), parent=None):
        self.xmlid = xmlid
        self.assigned_modifiers = list(mods)
        self.parent = parent
        self.main_power = None


def test_a_slot_reads_the_advantage_its_pool_carries():
    pool = _Power("MULTIPOWER", mods=[_Mod("ARMORPIERCING", levels=2)])
    slot = _Power(parent=pool)
    assert _has_modifier(slot, "ARMORPIERCING") is True
    assert _modifier_levels(slot, "ARMORPIERCING") == 2


def test_a_slot_does_not_read_the_pools_PRIVATE_modifier():
    """Those price the pool and do not reach its slots
    (``List.separatePrivateMods``)."""
    pool = _Power("MULTIPOWER", mods=[_Mod("PENETRATING", levels=1, private=True)])
    assert _has_modifier(_Power(parent=pool), "PENETRATING") is False


def test_a_modifier_inside_a_container_is_still_found():
    """A List holds its contents in ``objects``; a flat scan stops there."""
    class _List:
        xmlid = "LIST"
        def __init__(self, inner):
            self.objects, self.powers = inner, []

    p = _Power(mods=[_List([_Mod("HARDENED", levels=1)])])
    assert _modifier_levels(p, "HARDENED") == 1


def test_a_powers_own_modifier_still_wins_and_still_reads():
    """The narrow case the flat scan did handle must not regress."""
    p = _Power(mods=[_Mod("PENETRATING", levels=3)])
    assert _modifier_levels(p, "PENETRATING") == 3
    assert _modifier_levels(p, "ARMORPIERCING") == 0

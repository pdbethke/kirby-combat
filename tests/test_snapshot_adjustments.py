"""A Drain is applied once, not twice, across a snapshot round trip.

``to_dict`` recorded the CURRENT stat block — drains and aids already in it —
alongside the drains and aids dicts themselves. ``combat_stats()`` then applied
them to whatever the rehydrated hero reported, so every adjustment landed a
second time: Ravel with ``drains={"dex": 4}`` read DEX 15 live and 11 after a
round trip.

That is a replay-fidelity defect, not a cosmetic one. Replay folds forward from
a captured snapshot, so every recorded fight containing a Drain replayed with
the wrong numbers — and the numbers drive hit rolls.

The snapshot now records the block as it stands BEFORE application (the same
one ``combat_stats`` computes first, to read a Drain's floor off), written only
when there is something to apply.
"""
from __future__ import annotations

from kirby_combat.serialization import from_dict, to_dict
from tests.fixtures.synthetic_hero import synthetic_combatant


def _combatant(**kw):
    return synthetic_combatant(id="t", name="Test", dex=15, spd=4, pd=10, **kw)


def test_a_drain_survives_a_round_trip_without_being_applied_twice():
    hc = _combatant()
    hc.state.drains = {"dex": 4}
    live = hc.combat_stats().dex
    assert live == 11, "fixture drain did not take effect"
    assert from_dict(to_dict(hc)).combat_stats().dex == live


def test_an_aid_survives_a_round_trip_without_being_applied_twice():
    hc = _combatant()
    hc.state.aids = {"pd": 5}
    live = hc.combat_stats().pd
    assert live == 15, "fixture aid did not take effect"
    assert from_dict(to_dict(hc)).combat_stats().pd == live


def test_the_drains_themselves_still_travel():
    """The dict has to survive too — a drain RECOVERS over time, and recovery
    needs to know how much is outstanding."""
    hc = _combatant()
    hc.state.drains = {"dex": 4}
    assert from_dict(to_dict(hc)).state.drains == {"dex": 4}


def test_an_unadjusted_snapshot_carries_no_extra_block():
    """Written only when non-empty, so the common snapshot is unchanged."""
    assert "undrained" not in to_dict(_combatant())


def test_an_old_snapshot_is_reconstructed_rather_than_double_applied():
    """Recorded combats outlive the code that wrote them, so a snapshot from
    before the extra block must still replay. The pre-adjustment value is
    recovered by adding the recorded adjustment back — exact, except where a
    drain hit its floor and clamped, which destroys the amount really taken."""
    hc = _combatant()
    hc.state.drains = {"dex": 4}
    old = to_dict(hc)
    del old["undrained"]                      # a snapshot written before the fix
    assert from_dict(old).combat_stats().dex == hc.combat_stats().dex

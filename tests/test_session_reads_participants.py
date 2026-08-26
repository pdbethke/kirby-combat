"""session/ must read participants through the shared interface.

Measured 2026-08-25: session/ made zero combat_stats() calls and worked only
because the flat StatBlockCombatant answered `.dex` and `.spd` directly. That is the
no-op shim doing load-bearing work, and it is why step 3 of the April
migration looked done and was not.

This test uses an object that answers ONLY the shared interface -- no flat
attributes at all -- so it fails against any code path still reaching for
`.dex` on the combatant itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.session.timeline import build_acting_order_for_segment


@dataclass
class _StatsOnly:
    """A participant that exposes stats ONLY via combat_stats().

    `combat_stats` is attached per-instance in `_participant()` below, so
    there is deliberately no method here to shadow it, and no `_dex`/`_spd`
    fields -- the stat values live on the `_Stats` object that closure
    returns. Reading `.dex`/`.spd` off the participant raises instead.
    """
    id: str

    @property
    def dex(self) -> int:
        raise AssertionError(
            "session/ read .dex off the participant instead of combat_stats()"
        )

    @property
    def spd(self) -> int:
        raise AssertionError(
            "session/ read .spd off the participant instead of combat_stats()"
        )


class _Stats:
    def __init__(self, dex: int, spd: int):
        self.dex = dex
        self.spd = spd
        self.ego = 10
        self.int_ = 10
        self.pre = 10


def _participant(id_: str, dex: int, spd: int):
    p = _StatsOnly(id=id_)
    p.combat_stats = lambda: _Stats(dex, spd)
    return p


def test_acting_order_reads_through_combat_stats():
    fast = _participant("fast", dex=20, spd=4)
    slow = _participant("slow", dex=10, spd=4)

    order = build_acting_order_for_segment([fast, slow], segment=3)

    assert [s.combatant_id for s in order] == ["fast", "slow"], \
        "higher DEX acts first, and both must be read via combat_stats()"

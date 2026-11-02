"""`cover_half_move` reads Running off `movement_view`, as `_full_move` does.

It read `actor.hero.characteristic_value("RUNNING")`, which needs a build:
a combatant answering only the combatant-shaped question (`movement_view`)
could not be shown a Brief at all, because the threat picture's cover asks
for this Half Move. The two readings must agree for every real build before
the switch is trusted, so this walks the whole configured corpus.
"""
from __future__ import annotations

import pytest

from kirby_combat.enumeration import cover_half_move
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.synthetic import synthetic_combatant

from corpus import authored_root, require_authored


def _builds() -> list[str]:
    root = authored_root()
    if root is None:
        return []
    return sorted(p.stem for p in root.glob("*.json"))


@pytest.mark.parametrize("name", _builds() or [
    pytest.param("<unset>", marks=pytest.mark.skip(
        reason="KIRBY_COMBAT_BUILDS unset: no builds to compare"))])
def test_the_half_move_agrees_with_the_build_running(name):
    man = HeroCombatant.from_build(require_authored(name), id=name.lower())
    old = max(0.0, float(man.hero.characteristic_value("RUNNING") or 0) / 2.0)
    assert cover_half_move(man) == old


def test_a_synthetic_man_agrees_too():
    man = synthetic_combatant(id="m", name="M")
    old = max(0.0, float(man.hero.characteristic_value("RUNNING") or 0) / 2.0)
    assert cover_half_move(man) == old


class _NoRunning:
    def movement_view(self):
        return []


def test_a_man_with_no_running_entry_has_no_half_move():
    assert cover_half_move(_NoRunning()) == 0.0

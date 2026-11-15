"""A man someone is holding is not offered Hide.

Found 2026-11-15 recording Ravel against Bokor: Ravel Grabbed Bokor beside
a wall, and Bokor's menu offered "Hide -- break line-of-sight behind cover"
while Ravel had hold of him. The Hide gate asked only whether there was
cover in reach.

RULING: a Grab "immobilizes two of the target's limbs" and holds him
against the grabber (6E2 p.67-68), and Hide is breaking line of sight
behind cover. Nobody breaks line of sight from the man whose hands are on
him, so while Grabbed he is not offered Hide. The page does not name Hide;
the ruling is labelled where it is made.
"""
from __future__ import annotations

import pytest

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat import enumeration
from kirby_combat.enumeration import enumerate_actions


@pytest.fixture(autouse=True)
def beside_cover(monkeypatch):
    """Cover is in reach. Whether there is cover is `_actor_has_cover`'s
    question and has its own tests; this one is whether a held man may use
    it."""
    monkeypatch.setattr(enumeration, "_actor_has_cover", lambda actor, scene: True)


def _kinds(grabbed_by):
    hand = _StubPower(xmlid="HANDTOHANDATTACK", name="Mojo Hand", levels=6)
    bokor = _combatant(id="bokor", powers=[hand])
    ravel = _combatant(id="ravel", powers=[hand])
    return {a.kind for a in enumerate_actions(
        bokor, [ravel], grabbed_by=grabbed_by, distances={"ravel": 0.5})}


def test_a_free_man_beside_cover_may_hide():
    assert "hide" in _kinds(None)


def test_a_grabbed_man_beside_cover_may_not():
    kinds = _kinds("ravel")
    assert "hide" not in kinds
    assert "escape_str" in kinds   # he can still struggle

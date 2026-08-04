"""`is_mentalist` derives from owning a Mental Power (6E1 p150).

It was hardcoded ``return False`` from faa9c65 ("hero_view: step 6 partial"),
a placeholder in an unfinished migration that never got finished. Unlike the
two stubs beside it — ``is_npc`` and ``csls`` — it carried no comment saying
so, and therefore read as deliberate.

The cost of that was the entire mental-combat subsystem. Every mental power
gates on this property:

    mental/mental_blast.py:31      if not attacker.is_mentalist:
    mental/mental_illusion.py:44   if not attacker.is_mentalist:
    mental/mental_entangle.py:51   if not attacker.is_mentalist:
    mental/telepathy.py:35         if not attacker.is_mentalist:

So no character could use a Mental Power, ever. Proven live 2026-08-04: a
corpus villain (Slug) loaded with TELEPATHY among his powers, OMCV 6 — double
the base, so bought deliberately — and ``is_mentalist=False``. He spent the
fight punching a wall.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from kirby_combat.hero_view import MENTAL_POWER_XMLIDS, HeroCombatant


def _hero(*xmlids, nested=()):
    """A hero shell carrying the given powers, optionally inside a framework."""
    powers = [SimpleNamespace(xmlid=x, sub_powers=None) for x in xmlids]
    if nested:
        powers.append(SimpleNamespace(
            xmlid="MULTIPOWER",
            sub_powers=[SimpleNamespace(xmlid=x, sub_powers=None) for x in nested],
        ))
    return SimpleNamespace(powers=powers)


def _combatant(hero):
    c = HeroCombatant.__new__(HeroCombatant)
    object.__setattr__(c, "hero", hero)
    return c


def test_the_six_mental_powers_are_the_books_six() -> None:
    """6E1 p150 MENTAL POWERS lists exactly: Mental Blast, Mental Illusions,
    Mind Control, Mind Link, Mind Scan, Telepathy."""
    assert MENTAL_POWER_XMLIDS == frozenset({
        "EGOATTACK",        # Mental Blast
        "MENTALILLUSIONS",
        "MINDCONTROL",
        "MINDLINK",
        "MINDSCAN",
        "TELEPATHY",
    })


@pytest.mark.parametrize("xmlid", sorted(MENTAL_POWER_XMLIDS))
def test_owning_any_mental_power_makes_a_mentalist(xmlid) -> None:
    assert _combatant(_hero(xmlid)).is_mentalist is True


def test_a_brick_with_no_mental_powers_is_not_a_mentalist() -> None:
    assert _combatant(_hero("STR", "FORCEFIELD", "RUNNING")).is_mentalist is False


def test_mental_DEFENCE_alone_does_not_make_a_mentalist() -> None:
    """MENTALDEFENSE is a Defence Power and MENTALAWARENESS a Sense — neither
    is on 6E1 p150's list. Resisting mental attack is not the same as making
    one, and MENTALDEFENSE is the most common 'mental' xmlid in the corpus
    (230 instances), so getting this wrong would make half the roster
    mentalists."""
    c = _combatant(_hero("MENTALDEFENSE", "MENTALAWARENESS", "CLAIRSENTIENCE"))
    assert c.is_mentalist is False


def test_a_mental_power_inside_a_framework_still_counts() -> None:
    """Mentalists routinely buy their powers as multipower slots — Slug's own
    movement rig is a MULTIPOWER — so a shallow scan would miss them."""
    assert _combatant(_hero("STR", nested=("MINDSCAN",))).is_mentalist is True


def test_a_hero_with_no_powers_at_all_does_not_raise() -> None:
    assert _combatant(SimpleNamespace(powers=None)).is_mentalist is False
    assert _combatant(SimpleNamespace(powers=[])).is_mentalist is False


def test_xmlid_matching_is_case_insensitive() -> None:
    assert _combatant(_hero("telepathy")).is_mentalist is True

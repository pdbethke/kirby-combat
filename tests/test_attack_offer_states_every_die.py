"""An attack offer states the dice the roll will use, half dice and pips too.

The plain attack offer printed ``{damage_dice}d6K``, dropping ``half_die``
and ``plus_one`` -- so a 2½d6 attack was offered as "2d6" and Bokor's
Digitalis dust (an RKA bought at 0 dice plus a pip: 0d6+1 Killing, AVAD,
Damage Over Time) as "0d6K", which reads as an attack that does nothing.
The resolver has always rolled the half die and added the pip
(``resolution/damage.py``); only the page the chooser reads was wrong.
The Haymaker offer already wrote them, so the two shared nothing.
"""
from kirby_combat import enumerate_actions
from kirby_combat.enumeration import dice_label
from kirby_combat.hero_view import HeroCombatant
from types import SimpleNamespace

from tests.corpus import require_authored


def _attack(**kw) -> SimpleNamespace:
    """The four fields the roll reads, which are all the label reads."""
    base = dict(damage_dice=0, half_die=False, plus_one=False,
                damage_type="killing")
    base.update(kw)
    return SimpleNamespace(**base)


def test_whole_dice() -> None:
    assert dice_label(_attack(damage_dice=3)) == "3d6K"


def test_a_half_die() -> None:
    assert dice_label(_attack(damage_dice=2, half_die=True,
                              damage_type="normal")) == "2½d6N"


def test_a_pip() -> None:
    assert dice_label(_attack(damage_dice=0, plus_one=True)) == "0d6+1K"


def test_bokors_digitalis_dust_is_offered_as_what_it_rolls() -> None:
    bokor = HeroCombatant.from_build(require_authored("Bokor"))
    ravel = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    offers = [a.summary for a in enumerate_actions(bokor, [ravel])
              if a.kind == "attack" and "Digitalis" in a.summary]
    assert offers, "Digitalis dust should be on Bokor's menu"
    assert all("0d6+1K" in s for s in offers), offers

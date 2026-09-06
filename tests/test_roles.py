"""How a combatant is classified, and why the classification is load-bearing.

`classify_role` decides which tactical profile a combatant fights under. The
martial-artist branch carries a comment in its original home explaining the
cost of getting it wrong: abort-readiness gates a brawler OFF while it is at
or above 50% STUN, so misclassifying a martial artist makes it stubbornly eat
hits instead of aborting to its (e.g. +5) Martial Dodge.

The heuristics are debatable and deliberately unchanged by the move -- a
behaviour-preserving move is the only kind the existing fights can vouch for.
These tests pin the behaviour that exists, not the behaviour that would be
better.
"""
import itertools
from dataclasses import dataclass, field

from kirby_combat.roles import ROLES, classify_role

_IDS = itertools.count(7_000_001)


@dataclass
class _Power:
    xmlid: str
    range_m: float = 0.0
    id: int = field(default_factory=lambda: next(_IDS))


@dataclass
class _Maneuver:
    is_attack: bool = False
    is_dodge: bool = False
    is_block: bool = False


class _Combatant:
    """The narrowest thing classify_role can be asked about: some attacks and
    a maneuver view. It reads nothing else -- no session, no rows."""

    def __init__(self, attacks=(), maneuvers=()):
        self.attacks = list(attacks)
        self._maneuvers = list(maneuvers)

    def maneuver_view(self):
        return self._maneuvers


def test_the_five_roles_are_the_whole_vocabulary():
    assert set(ROLES) == {
        "controller", "support", "ranged_blaster", "martial_artist",
        "aggressive_brawler",
    }


def test_a_mental_attack_makes_a_controller():
    assert classify_role(_Combatant([_Power("MINDCONTROL")])) == "controller"


def test_first_match_wins_mental_beats_range():
    """A long-ranged mental attack is a controller, not a blaster: the
    decision tree is ordered, and the order is the rule."""
    actor = _Combatant([_Power("MINDCONTROL", range_m=200)])
    assert classify_role(actor) == "controller"


def test_a_support_power_makes_support():
    assert classify_role(_Combatant([_Power("HEALING")])) == "support"


def test_long_range_makes_a_ranged_blaster():
    assert classify_role(_Combatant([_Power("BLAST", range_m=100)])) == "ranged_blaster"


def test_the_range_threshold_is_fifty_metres_inclusive():
    """50 is the boundary and it is inclusive. Pinned because it is a magic
    number: nothing in the rulebook says 50, so only this test says it."""
    assert classify_role(_Combatant([_Power("BLAST", range_m=50)])) == "ranged_blaster"
    assert classify_role(_Combatant([_Power("BLAST", range_m=49.9)])) != "ranged_blaster"


def test_martial_maneuvers_make_a_martial_artist():
    actor = _Combatant([_Power("HANDTOHANDATTACK")], [_Maneuver(is_dodge=True)])
    assert classify_role(actor) == "martial_artist"


def test_any_of_attack_dodge_or_block_counts():
    for kw in ("is_attack", "is_dodge", "is_block"):
        actor = _Combatant([_Power("HKA")], [_Maneuver(**{kw: True})])
        assert classify_role(actor) == "martial_artist", kw


def test_no_powers_at_all_is_a_brawler_not_a_crash():
    assert classify_role(_Combatant()) == "aggressive_brawler"


def test_a_broken_maneuver_view_does_not_break_classification():
    """maneuver_view is best-effort in the original and stays so here: a
    combatant whose view raises still classifies, as a brawler."""

    class _Broken(_Combatant):
        def maneuver_view(self):
            raise RuntimeError("no engine view")

    assert classify_role(_Broken([_Power("STRIKE")])) == "aggressive_brawler"

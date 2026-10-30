"""Out of END, he pays in STUN (6E2 p.133).

"A character who runs out of END ... and still wishes to perform Actions may
use STUN as END. The character takes 1d6 STUN Only damage for every 2 'END'
(or fraction thereof) used, and no defense is allowed against this damage.
Yes, characters can Knock themselves Out using this rule ... Characters
cannot spend END below 0."

`spend_end` clamped at zero and charged nothing past it, so a man with no
END fired for free for the rest of the fight (engine 0.24.0: Bullet emptied
his END in Turn 10 and kept blasting every Phase to the cap).
"""
from __future__ import annotations

from kirby_dice import FakeRoller

from kirby_combat.endurance import spend_end
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_SUPERHEROIC


def _session(*, end: int, stun: int = 30, dice=()):
    man = synthetic_combatant(
        id="m", name="m", spd=4, max_stun=30, current_stun=stun,
        max_end=30, current_end=end, side=Side.named("a"))
    other = synthetic_combatant(id="o", name="o", spd=4, side=Side.named("b"))
    return CombatSession.create(
        id="s", combatants=[man, other], scene=None,
        template=RAW_SUPERHEROIC, dice_roller=FakeRoller(list(dice)),
    ).start()


def _rows(session):
    return [(e.stun, e.end, e.reason) for e in session.event_log
            if e.kind == "VitalsChanged" and e.combatant_id == "m"]


def test_what_he_has_is_spent_as_before():
    out = spend_end(_session(end=10), "m", 4)
    assert _rows(out) == [(0, -4, "end_spent")]


def test_past_zero_each_two_end_or_fraction_is_a_d6_of_stun():
    """2 END in hand, 5 to pay: the 2 are spent, the other 3 are 2d6 STUN."""
    out = spend_end(_session(end=2, dice=[[4, 3]]), "m", 5)
    assert _rows(out) == [(0, -2, "end_spent"), (-7, 0, "stun_for_end")]
    m = out.combatants["m"]
    assert (m.current_end, m.current_stun) == (0, 23)


def test_at_zero_it_is_all_stun_and_end_never_goes_below_zero():
    out = spend_end(_session(end=0, dice=[[6]]), "m", 1)
    assert _rows(out) == [(-6, 0, "stun_for_end")]
    assert out.combatants["m"].current_end == 0


def test_he_can_knock_himself_out():
    """ "Yes, characters can Knock themselves Out using this rule." """
    out = spend_end(_session(end=0, stun=4, dice=[[5, 5]]), "m", 4)
    assert out.combatants["m"].current_stun == -6

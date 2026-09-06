"""Sides — including the four-army case and the free-for-all default."""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.loop.sides import last_side_standing, side_of, standing_sides
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _c(id: str, *, side: str | None = None, stun: int = 30, body: int = 12):
    return synthetic_combatant(
        id=id, name=id, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=12, max_end=30,
        current_stun=stun, current_body=body, current_end=30,
        side=side,
    )


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(combatants), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()


# ---- side_of: the default that carries the whole design ----

def test_an_explicit_side_is_used_as_given():
    assert side_of(_c("a", side="heroes")) == "heroes"


def test_no_side_means_a_side_of_one():
    assert side_of(_c("a")) == "solo:a"
    assert side_of(_c("b")) == "solo:b"
    assert side_of(_c("a")) != side_of(_c("b"))


# ---- Two teams ----

def test_two_teams_are_not_over_while_both_stand():
    s = _session(_c("a", side="heroes"), _c("b", side="villains"))
    assert last_side_standing(s) == (False, None)


def test_two_teams_end_when_one_is_down():
    s = _session(_c("a", side="heroes"), _c("b", side="villains", stun=0))
    assert last_side_standing(s) == (True, "heroes")


def test_a_side_survives_while_any_member_stands():
    s = _session(
        _c("a1", side="heroes"), _c("a2", side="heroes", stun=-5),
        _c("b1", side="villains", stun=0),
    )
    assert last_side_standing(s) == (True, "heroes")


# ---- Three, and four ----

def test_a_three_way_runs_until_one_side_remains():
    s = _session(_c("a", side="a"), _c("b", side="b"), _c("c", side="c"))
    assert last_side_standing(s) == (False, None)

    s = _session(_c("a", side="a"), _c("b", side="b", stun=0), _c("c", side="c"))
    assert last_side_standing(s) == (False, None), "two sides left is not over"

    s = _session(
        _c("a", side="a"), _c("b", side="b", stun=0), _c("c", side="c", stun=-3),
    )
    assert last_side_standing(s) == (True, "a")


def test_the_battle_of_four_armies():
    """Four sides, several soldiers each. The fight ends when three armies
    are down, however many soldiers the fourth still has."""
    roster = []
    for army in ("red", "blue", "green", "gold"):
        for n in range(3):
            roster.append(_c(f"{army}{n}", side=army))
    s = _session(*roster)
    assert len(standing_sides(s)) == 4
    assert last_side_standing(s) == (False, None)

    # Wipe three armies; gold keeps all three soldiers.
    downed = [
        _c(c.id, side=c.side, stun=0) if c.side != "gold" else c
        for c in s.combatants.values()
    ]
    s = _session(*downed)
    assert last_side_standing(s) == (True, "gold")
    assert len(standing_sides(s)["gold"]) == 3


# ---- The free-for-all this default exists to protect ----

def test_an_unlabelled_free_for_all_is_not_over_at_phase_zero():
    """The defect a shared "default" side would have caused: every fighter
    on one team, so the fight is decided before anyone acts."""
    s = _session(_c("a"), _c("b"), _c("c"))
    assert last_side_standing(s) == (False, None)
    assert len(standing_sides(s)) == 3


def test_an_unlabelled_free_for_all_ends_with_one_fighter_left():
    s = _session(_c("a"), _c("b", stun=0), _c("c", body=0))
    assert last_side_standing(s) == (True, "solo:a")


def test_a_team_plus_two_loners():
    s = _session(_c("p1", side="pack"), _c("p2", side="pack"), _c("x"), _c("y"))
    assert len(standing_sides(s)) == 3

    s = _session(
        _c("p1", side="pack"), _c("p2", side="pack"), _c("x", stun=0), _c("y", stun=0),
    )
    assert last_side_standing(s) == (True, "pack")


# ---- Everyone down ----

def test_a_mutual_knockout_is_over_with_no_winner():
    s = _session(_c("a", side="heroes", stun=0), _c("b", side="villains", stun=-4))
    assert last_side_standing(s) == (True, None)


def test_body_at_zero_counts_as_down():
    """6E1 p.421 — dying at BODY <= 0, not only KO'd at STUN <= 0."""
    s = _session(_c("a", side="heroes"), _c("b", side="villains", body=0))
    assert last_side_standing(s) == (True, "heroes")

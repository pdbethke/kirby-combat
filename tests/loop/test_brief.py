"""``Brief`` — one Phase, written down.

The last thing keeping a fight inside the parked wrapper. Its equivalent
there was already a pure function of engine state, measured to touch the
database zero times; only its location was wrong.
"""
from __future__ import annotations

import pytest

from conftest import fighter, encounter_of  # tests/loop/conftest.py
from kirby_combat.brief import Brief, CombatantLine
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop import PhaseSituation, Roster
from kirby_combat.side import Side


def _situation(*, actor_side="heroes", enemy_side="villains") -> PhaseSituation:
    enc = encounter_of(
        fighter("aurora", side=Side.named(actor_side), dex=25),
        fighter("bulwark", side=Side.named(actor_side), dex=20),
        fighter("nemesis", side=Side.named(enemy_side), dex=15),
    )
    session = enc.sessions[0]
    actor = session.combatants["aurora"]
    roster = Roster(session)
    enemies = roster.enemies_of(actor)
    return PhaseSituation(
        actor=actor, menu=enumerate_actions(actor, enemies),
        enemies=enemies, allies=roster.allies_of(actor),
        session=session, segment=12, turn=1,
    )


# ---- The contract: ids are what a chooser returns ----

def test_every_offered_action_appears_with_its_id():
    """The bracketed token is the contract --- `validate_choice` checks
    against exactly these. The summary is for the reader."""
    brief = Brief(_situation())
    text = brief.render()
    for action in brief.menu:
        assert f"[{action.action_id}]" in text


def test_action_ids_match_the_menu_exactly():
    brief = Brief(_situation())
    assert brief.action_ids == [a.action_id for a in brief.menu]


def test_the_count_is_the_number_of_offers():
    brief = Brief(_situation())
    assert len(brief) == len(brief.menu) > 0


def test_the_stated_count_matches_what_is_listed():
    brief = Brief(_situation())
    text = brief.render()
    assert f"Legal actions this Phase ({len(brief)})" in text
    assert text.count("\n  [") == len(brief)


# ---- Who is described ----

def test_the_actor_is_named_as_the_one_being_controlled():
    assert "YOU control: aurora" in Brief(_situation()).render()


def test_allies_and_enemies_are_separated_by_side():
    brief = Brief(_situation())
    assert [line.name for line in brief.allies] == ["bulwark"]
    assert [line.name for line in brief.enemies] == ["nemesis"]

    text = brief.render()
    assert "Allies:" in text and "Enemies:" in text
    assert text.index("Allies:") < text.index("Enemies:")


def test_a_solo_actor_gets_no_allies_section():
    enc = encounter_of(fighter("a", dex=25), fighter("b", dex=15))
    session = enc.sessions[0]
    actor = session.combatants["a"]
    roster = Roster(session)
    brief = Brief(PhaseSituation(
        actor=actor, menu=enumerate_actions(actor, roster.enemies_of(actor)),
        enemies=roster.enemies_of(actor), allies=roster.allies_of(actor),
        session=session, segment=12, turn=1,
    ))
    assert brief.allies == []
    assert "Allies:" not in brief.render()


def test_no_standing_enemies_is_said_rather_than_left_blank():
    enc = encounter_of(
        fighter("a", side=Side.named("x"), dex=25),
        fighter("b", side=Side.named("y"), stun=0),
    )
    session = enc.sessions[0]
    actor = session.combatants["a"]
    roster = Roster(session)
    brief = Brief(PhaseSituation(
        actor=actor, menu=enumerate_actions(actor, roster.enemies_of(actor)),
        enemies=roster.enemies_of(actor), allies=roster.allies_of(actor),
        session=session, segment=12, turn=1,
    ))
    assert "Enemies: none standing." in brief.render()


# ---- The state line ----

def test_a_combatant_line_carries_vitals_cvs_side_and_role():
    line = CombatantLine(_situation().actor)
    text = line.render()
    for fragment in ("STUN", "BODY", "END", "OCV", "DCV", "role=", "[heroes]"):
        assert fragment in text, f"{fragment!r} missing from {text!r}"


def test_the_turn_and_segment_lead():
    assert Brief(_situation()).render().startswith("Turn 1, Segment 12.")


def test_str_is_the_rendered_page():
    brief = Brief(_situation())
    assert str(brief) == brief.render()


def test_a_downed_combatant_is_marked():
    down = fighter("fallen", side=Side.named("x"), stun=0)
    assert CombatantLine(down).is_down
    assert CombatantLine(down).render().endswith("-- DOWN")


def test_enemy_numbers_are_shown_as_freely_as_the_actors():
    """Deliberate: the anti-metagaming line is drawn by PERCEPTION, not by
    hiding stat blocks from whoever is choosing."""
    brief = Brief(_situation())
    assert "STUN" in brief.enemies[0].render()


# ---- It is a view, not a rule: no state is touched ----

def test_rendering_changes_nothing():
    situation = _situation()
    before = situation.actor.state.current_stun
    Brief(situation).render()
    assert situation.actor.state.current_stun == before


def test_rendering_is_deterministic():
    situation = _situation()
    assert Brief(situation).render() == Brief(situation).render()

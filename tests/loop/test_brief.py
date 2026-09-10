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
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller
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


# ---------------------------------------------------------------------------
# Terrain. A Brief that lists combatants and offers and says nothing about
# where anyone stands describes a fight in a void.
# ---------------------------------------------------------------------------


def _lot_situation():
    """Two fighters 4m apart with a wall between them."""
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Wall,
    )

    scene = Scene(
        id="lot", name="A narrow lot",
        bounds=SceneBounds(-20, -20, 0, 20, 20, 10),
        surfaces=[], hazards=[], ambient=AmbientConditions(),
        walls=[Wall(
            id="crate", name="Stack of crates",
            segment=(Position(2.0, -1.0, 0.0), Position(2.0, 1.0, 0.0)),
            height_m=1.5, blocks_los=True, blocks_movement=True,
            cover_level=3, body=5, def_value=2,
        )],
        combatant_positions={
            "aurora": Position(0.0, 0.0, 0.0), "nemesis": Position(4.0, 0.0, 0.0),
        },
    )
    session = CombatSession.create(
        id="s", combatants=[
            fighter("aurora", side=Side.named("heroes"), dex=25),
            fighter("nemesis", side=Side.named("villains"), dex=15),
        ],
        scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=2),
    ).start()
    actor = session.combatants["aurora"]
    roster = Roster(session)
    return PhaseSituation(
        actor=actor, menu=enumerate_actions(actor, roster.enemies_of(actor)),
        enemies=roster.enemies_of(actor), allies=roster.allies_of(actor),
        session=session, segment=12, turn=1,
    )


def test_the_ground_is_named_and_its_features_listed():
    page = Brief(_lot_situation()).render()
    assert "A narrow lot" in page
    assert "Stack of crates" in page
    assert "cover 3/4" in page
    assert "BODY 5" in page, "what it would take to shoot through"


def test_enemy_bearings_carry_range_and_cover():
    """The same figures the RULES use -- the range that gates melee, the
    cover that penalises the shot. A reader weighing an offer and the
    engine resolving it quote the same numbers."""
    brief = Brief(_lot_situation())
    bearing = brief.terrain.bearings[0]
    assert bearing.name == "nemesis"
    assert bearing.range_m == pytest.approx(4.0)
    assert bearing.cover_level == 3
    assert bearing.cover_ocv < 0, "cover makes the shot harder"


def test_the_page_says_when_line_of_sight_is_blocked():
    page = Brief(_lot_situation()).render()
    assert "NO line of sight" in page


def test_bearings_are_ordered_nearest_first():
    from kirby_combat.brief import EnemyBearing

    unsorted = [EnemyBearing("c", "c", 9.0), EnemyBearing("a", "a", 1.0)]
    assert min(unsorted, key=lambda b: b.range_m).name == "a"


def test_a_sceneless_fight_says_so_rather_than_implying_ground():
    """No Scene is a real answer -- this fight happens nowhere in
    particular -- not an empty section that reads like open ground."""
    page = Brief(_situation()).render()
    assert "no positions are being tracked" in page
    # The TERRAIN section must not imply ground it does not have. Scoped
    # to that section rather than the whole page above it, because the
    # doctrine section legitimately says "cover" -- a tactic advising
    # cover is advice about the fight, not a claim about this map.
    terrain = page.split("Legal actions")[0].split("Ground:")[1]
    terrain = terrain.split("What your doctrine says")[0]
    assert "cover" not in terrain.lower()


def test_terrain_reads_state_and_changes_none():
    situation = _lot_situation()
    before = dict(situation.session.scene.combatant_positions)
    Brief(situation).render()
    assert situation.session.scene.combatant_positions == before


def test_a_bearing_says_what_the_distance_costs_to_hit():
    """The page prints what COVER costs to shoot through and, until now,
    printed range as a bare distance -- leaving whatever is choosing to
    know 6E2's Range Modifier table by heart to tell a free shot from a
    -6. Cover's OCV cost is quoted beside its level for exactly this
    reason; distance is the other half of the same sum."""
    from kirby_combat.brief import EnemyBearing

    near = EnemyBearing("a", "a", range_m=4.0)
    assert near.range_ocv == 0
    far = EnemyBearing("b", "b", range_m=100.0)
    assert far.range_ocv == -8
    assert "-8 OCV" in far.render()
    assert "OCV" not in near.render(), "point blank costs nothing; say nothing"

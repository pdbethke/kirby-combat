"""The turn loop, driving fights to decisions with no database and no HTTP."""
from __future__ import annotations

import pytest

from conftest import encounter_of, fighter, session_of  # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.loop import (
    FirstLegalChooser, InvalidChoice, PhaseSituation, Roster, TacticChooser,
    UnresolvableAction, Verdict, next_actor_id, registered_kinds,
    run_encounter, run_phase,
)
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


# ---- The registry's gap, asserted so it is a number that moves ----

def test_the_registered_kinds_are_pinned():
    """52 kinds are enumerable; these are the ones the engine can execute.
    This set GROWING is the measure of the driver carve-out's progress --
    when a resolver migrates out of the parked kirby-api driver, this
    assertion is what says so."""
    assert registered_kinds() == frozenset(
        {"attack", "strike", "mental_blast", "recover"}
    )


def test_an_unregistered_kind_raises_and_names_itself():
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import resolve_chosen

    action = LegalAction(
        action_id="dodge:", kind="dodge", target_id=None,
        power_xmlid=None, power_name=None, summary="Dodge",
    )
    with pytest.raises(UnresolvableAction, match="dodge"):
        resolve_chosen(
            session_of(fighter("a")), fighter("a"), action,
            template=TEMPLATE, roller=RandomRoller(seed=1),
        )


# ---- One Phase ----

def test_run_phase_reports_no_actor_before_an_order_is_resolved():
    """`run_segment` writes the acting order; without it there are no
    slots and the loop's signal is `actor_id is None`."""
    result = run_phase(
        session_of(fighter("a", side=Side.named("x")), fighter("b", side=Side.named("y"))),
        FirstLegalChooser(), template=TEMPLATE, roller=RandomRoller(seed=1),
    )
    assert result.actor_id is None
    assert result.acted is False


def test_run_phase_spends_one_slot_and_deals_damage():
    enc = encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y"), dex=10))
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    before = enc.sessions[0].combatants["b"].state.current_stun
    result = run_phase(
        enc.sessions[0], FirstLegalChooser(), template=TEMPLATE, roller=roller,
    )

    assert result.actor_id == "a", "highest DEX acts first (6E2 p.19)"
    assert result.acted
    assert result.kind in ("attack", "strike")
    assert result.events, "the Phase must produce events for a consumer to extrude"
    assert result.session.combatants["b"].state.current_stun < before


def test_a_spent_slot_is_not_offered_again():
    enc = encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y"), dex=10))
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    first = run_phase(enc.sessions[0], FirstLegalChooser(), template=TEMPLATE, roller=roller)
    second = run_phase(first.session, FirstLegalChooser(), template=TEMPLATE, roller=roller)
    assert (first.actor_id, second.actor_id) == ("a", "b")

    third = run_phase(second.session, FirstLegalChooser(), template=TEMPLATE, roller=roller)
    assert third.actor_id is None, "both slots are spent"


def test_a_downed_combatant_is_skipped_not_asked():
    """6E1 p.421. Their slot is consumed -- they had a Phase and are in no
    condition to use it -- but they are never enumerated for."""
    enc = encounter_of(
        fighter("a", side=Side.named("x"), dex=25), fighter("down", side=Side.named("y"), dex=10, stun=0),
    )
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    assert next_actor_id(enc.sessions[0]) == "a"
    # `on_unresolvable="skip"` because with its only enemy down, "a" has no
    # attack to offer -- the menu opens with Dodge, which the engine cannot
    # yet resolve. That is this test's incidental surface, not its subject.
    first = run_phase(
        enc.sessions[0], FirstLegalChooser(), template=TEMPLATE, roller=roller,
        on_unresolvable="skip",
    )
    assert next_actor_id(first.session) is None


# ---- The seat ----

def test_a_choice_outside_the_menu_raises_at_the_seat():
    class Liar:
        def choose(self, situation: PhaseSituation) -> str:
            return "attack:nobody:nothing"

    enc = encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y")))
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    with pytest.raises(InvalidChoice, match="not offered"):
        run_phase(enc.sessions[0], Liar(), template=TEMPLATE, roller=roller)


def test_the_chooser_sees_enemies_by_side_not_by_id():
    seen: list[PhaseSituation] = []

    class Spy:
        def choose(self, situation: PhaseSituation) -> str:
            seen.append(situation)
            return situation.menu[0].action_id

    enc = encounter_of(
        fighter("a1", side=Side.named("pack"), dex=25), fighter("a2", side=Side.named("pack"), dex=24),
        fighter("b", side=Side.named("loner"), dex=10),
    )
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))
    run_phase(enc.sessions[0], Spy(), template=TEMPLATE, roller=roller)

    situation = seen[0]
    assert [c.id for c in situation.enemies] == ["b"]
    assert [c.id for c in situation.allies] == ["a2"]


def test_the_tactic_chooser_picks_something_legal():
    """Doctrine may recommend a kind the actor cannot perform this Phase;
    enumeration has already ruled on legality, so the chooser must return
    something from the menu it was given, whatever the tactics said."""
    enc = encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y")))
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    result = run_phase(enc.sessions[0], TacticChooser(), template=TEMPLATE, roller=roller)
    assert result.acted


# ---- Unresolvable-kind policy ----

def test_skip_records_the_kind_rather_than_hiding_it():
    class AlwaysDodge:
        def choose(self, situation: PhaseSituation) -> str:
            for action in situation.menu:
                if action.kind == "dodge":
                    return action.action_id
            return situation.menu[0].action_id

    enc = encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y")))
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    result = run_phase(
        enc.sessions[0], AlwaysDodge(), template=TEMPLATE, roller=roller,
        on_unresolvable="skip",
    )
    assert result.skipped_kind == "dodge"
    assert result.acted is False
    assert result.notes, "a skip must never be silent"


def test_an_unknown_policy_is_rejected():
    with pytest.raises(ValueError, match="on_unresolvable"):
        run_phase(
            session_of(fighter("a")), FirstLegalChooser(),
            template=TEMPLATE, roller=RandomRoller(seed=1),
            on_unresolvable="ignore",
        )


# ---- Whole fights ----

def test_a_duel_reaches_a_decision():
    enc = encounter_of(fighter("hero", side=Side.named("heroes"), dex=23),
                       fighter("villain", side=Side.named("villains"), dex=18))
    result = run_encounter(
        enc, FirstLegalChooser(), roller=RandomRoller(seed=7),
        on_unresolvable="skip", max_turns=10,
    )
    assert result.complete
    assert result.winner in (Side.named("heroes"), Side.named("villains"))
    assert result.phases > 0
    verdict = Roster(result.encounter.sessions[0]).decide()
    assert verdict == Verdict(over=True, winner=result.winner)


def test_a_four_way_free_for_all_ends_with_one_fighter():
    """Nobody carries a side label, so each fighter is their own side."""
    enc = encounter_of(*[fighter(n, dex=20 + i) for i, n in enumerate("abcd")])
    result = run_encounter(
        enc, FirstLegalChooser(), roller=RandomRoller(seed=11),
        on_unresolvable="skip", max_turns=20,
    )
    assert result.complete
    assert result.winner is None or result.winner.is_solo


def test_the_battle_of_four_armies():
    roster = [
        fighter(f"{army}{n}", side=Side.named(army), dex=20 + n)
        for army in ("red", "blue", "green", "gold")
        for n in range(2)
    ]
    result = run_encounter(
        encounter_of(*roster), FirstLegalChooser(),
        roller=RandomRoller(seed=5), on_unresolvable="skip", max_turns=25,
    )
    if result.complete:
        assert result.winner is None or result.winner.name in ("red", "blue", "green", "gold")
    else:
        assert result.notes, "an undecided fight must say why it stopped"


def test_a_caller_supplied_stop_condition_replaces_last_side_standing():
    """First blood: over the moment anyone has taken a point of STUN."""
    class FirstBlood:
        """A caller's own rule, as a class -- the StopCondition protocol."""

        def decide(self, roster):
            for c in roster.combatants:
                if c.state.current_stun < c.combat_stats().max_stun:
                    return Verdict(over=True, winner=Side.of(c))
            return Verdict(over=False)

    result = run_encounter(
        encounter_of(fighter("a", side=Side.named("x"), dex=25), fighter("b", side=Side.named("y"))),
        FirstLegalChooser(), roller=RandomRoller(seed=3),
        until=FirstBlood(), on_unresolvable="skip", max_turns=5,
    )
    assert result.complete
    assert result.phases == 1, "one landed hit should end a first-blood fight"


def test_an_already_decided_fight_returns_before_any_phase():
    result = run_encounter(
        encounter_of(fighter("a", side=Side.named("x")), fighter("b", side=Side.named("y"), stun=0)),
        FirstLegalChooser(), roller=RandomRoller(seed=1),
    )
    assert result.complete and result.winner == Side.named("x")
    assert result.phases == 0
    assert "already decided" in " ".join(result.notes)


def test_the_max_turns_guard_stops_rather_than_looping():
    """Two combatants who cannot hurt each other must not spin forever."""
    result = run_encounter(
        encounter_of(fighter("a", side=Side.named("x"), dice=1), fighter("b", side=Side.named("y"), dice=1)),
        FirstLegalChooser(), roller=RandomRoller(seed=2),
        on_unresolvable="skip", max_turns=2,
    )
    assert result.complete is False
    assert "guard" in " ".join(result.notes)


def test_a_fight_is_deterministic_for_a_seed():
    def run():
        return run_encounter(
            encounter_of(fighter("a", side=Side.named("x"), dex=23), fighter("b", side=Side.named("y"), dex=18)),
            FirstLegalChooser(), roller=RandomRoller(seed=99),
            on_unresolvable="skip", max_turns=10,
        )
    first, second = run(), run()
    assert (first.complete, first.winner, first.phases) == (
        second.complete, second.winner, second.phases
    )

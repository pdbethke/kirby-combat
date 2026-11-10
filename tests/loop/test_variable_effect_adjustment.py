"""A Variable Effect Drain is offered, and the seat names what it drains.

6E1 p.144-145: Variable Effect (+1/2) lets a character "switch which
Characteristic(s) and/or Power(s) it can affect from use to use" within a
defined category; with Expanded Effect he affects that many "at once"
(p.144: two is +1/2, each more another +1/2, so HD's LEVELS is the count).

FOUND 2026-11-10: Plague (CV3) never used his Drain in a fight. His Acute
Disease is ``Drain, INPUT "any two characteristics at once", Variable Effect,
Expanded Effect x2``. The INPUT names no characteristic, so
`characteristic_targets` said None and the menu dropped the power, silently.

There are 17 characteristics, so "any two" is 136 pairs per enemy. Rather
than 136 menu lines, the engine offers ONE Drain per enemy that carries the
choice (`LegalAction.choice`), and the seat answers with the offer id plus
``=A+B``. `validate_choice` holds the answer to the rule: the right count,
distinct, each one the power may reach. The bare offer id is not an answer.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.adjustments import characteristic_choice
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.chooser import (
    FirstLegalChooser, InvalidChoice, complete_choice, validate_choice,
)
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()
HEROES, VILLAINS = Side.named("heroes"), Side.named("villains")
HIT = [1, 1, 1]


class _Disease:
    """Plague's Acute Disease, in the shape the loader gives enumeration."""

    def __init__(self, *, input: str = "any two characteristics at once",
                 variable: bool = True, expanded: int | None = 2, levels: int = 2):
        self.xmlid = "DRAIN"
        self.name = self.alias = "Acute Disease"
        self.id = "src-disease"
        self.levels = levels
        self.level_value = 1.0
        self.input = input
        self.range = "Yes"
        self.range_value = 100
        self.active_cost = levels * 10
        self.assigned_adders: list = []
        mods = []
        if variable:
            mods.append(SimpleNamespace(xmlid="VARIABLEEFFECT", levels=0))
        if expanded is not None:
            mods.append(SimpleNamespace(xmlid="EXPANDEDEFFECT", levels=expanded))
        self.assigned_modifiers = mods
        self.sub_powers: list = []


def _plague(**kw):
    c = fighter("plague", side=VILLAINS)
    c.hero.powers.append(_Disease(**kw))
    return c


def _session(*cast) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(cast), scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


def _menu(session, actor_id="plague"):
    actor = session.combatants[actor_id]
    others = [c for c in session.combatants.values() if c.id != actor_id]
    return enumerate_actions(actor, [c for c in others if c.side != actor.side],
                             allies=[c for c in others if c.side == actor.side])


def _drains(menu):
    return [a for a in menu if a.kind == "drain"]


# ── What the power is ───────────────────────────────────────────────────────

def test_plagues_disease_chooses_two_of_every_characteristic() -> None:
    choice = characteristic_choice(_Disease())
    assert choice.count == 2
    assert {"STR", "DEX", "CON", "BODY", "STUN", "SPD", "EGO", "PRE"} <= set(choice.domain)
    assert len(choice.domain) == len(set(choice.domain)) == 17


def test_without_expanded_effect_he_chooses_one() -> None:
    assert characteristic_choice(_Disease(input="Characteristics", expanded=None)).count == 1


def test_without_variable_effect_there_is_no_choice() -> None:
    """p.144: without Variable Effect "the character must define which game
    elements he affects when he buys the Adjustment Power" --- an INPUT that
    names none is still not built."""
    assert characteristic_choice(_Disease(variable=False)) is None


def test_a_special_effect_group_is_not_a_characteristic_choice() -> None:
    """"Fire Powers" needs every power's special effect, which no build
    carries; it stays unbuilt rather than guessed at."""
    assert characteristic_choice(_Disease(input="Fire Powers")) is None


# ── The offer ───────────────────────────────────────────────────────────────

def test_one_drain_per_enemy_carrying_the_choice() -> None:
    session = _session(_plague(), fighter("agent1", side=HEROES),
                       fighter("agent2", side=HEROES))
    drains = _drains(_menu(session))
    assert sorted(a.target_id for a in drains) == ["agent1", "agent2"]
    assert all(a.choice is not None and a.choice.count == 2 for a in drains)
    assert "2" in drains[0].summary and "STUN" in drains[0].summary


def test_the_bare_offer_is_not_an_answer() -> None:
    session = _session(_plague(), fighter("agent1", side=HEROES))
    offer = _drains(_menu(session))[0]
    with pytest.raises(InvalidChoice, match="names"):
        validate_choice(offer.action_id, _menu(session))


@pytest.mark.parametrize("picked", [("CON",), ("CON", "DEX", "STR"), ("CON", "CON"),
                                    ("CON", "LUCK")])
def test_an_answer_off_the_rule_is_refused(picked) -> None:
    session = _session(_plague(), fighter("agent1", side=HEROES))
    offer = _drains(_menu(session))[0]
    with pytest.raises(InvalidChoice):
        validate_choice(f"{offer.action_id}={'+'.join(picked)}", _menu(session))


def test_a_completed_answer_drains_both_at_full_effect() -> None:
    """p.144 Expanded Effect: "full effect against two or more game elements
    simultaneously". 12 points: DEX loses 12/2 = 6 (p.137); CON is a
    defensive characteristic, halved (p.143), and costs 1 a point."""
    session = _session(_plague(), fighter("agent1", side=HEROES, dex=20))
    menu = _menu(session)
    action = validate_choice(complete_choice(_drains(menu)[0], ["DEX", "CON"]), menu)
    assert action.action_id.endswith("=DEX+CON")
    after = resolve_chosen(session, session.combatants["plague"], action,
                           template=TEMPLATE, roller=FakeRoller([HIT, [6, 6]])).session
    stats = after.combatants["agent1"].combat_stats()
    assert stats.dex == 14
    assert stats.con == 18 - 6


def test_the_first_legal_chooser_completes_a_choice_it_takes_first() -> None:
    """The test seat must never hand the loop an unfinished offer."""
    session = _session(_plague(), fighter("agent1", side=HEROES))
    menu = [a for a in _menu(session) if a.kind == "drain"]
    situation = SimpleNamespace(menu=menu, ordered_menu=menu)
    picked = FirstLegalChooser().choose(situation)
    assert validate_choice(picked, menu).action_id == picked

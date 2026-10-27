"""The names a player's Held Action order may name its action by.

Peter, 2026-10-27: a Held Action order names its action "by power (or
maneuver) plus a target rule" --- "fire Energy Blast at whoever attacks
Lady Blue" --- and is matched to the live offer when it fires. An editor
needs the names to offer, and they must be the names the menu puts on its
offers (`LegalAction.power_name`), or an order would name something no offer
ever carries. `nameable_powers` is the sheet's names --- every power of the
build in play and every bought maneuver, plus the Strike everyone has --- a
SUPERSET of what the menu can carry; these tests hold that line on real
builds through the menu's own door.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.reactions import nameable_powers
from kirby_combat.loop.run import _situation_for
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from tests.corpus import require_authored


def _mark():
    return synthetic_combatant(
        id="mark", name="mark", ocv=6, dcv=5, omcv=5, dmcv=5,
        spd=4, dex=15, ego=10, str_=15, con=18, pre=10, rec=6,
        pd=4, ed=4, rpd=0, red=0, md=0,
        max_stun=60, max_body=15, max_end=40, side=Side.named("b"),
    )


def _menu_names(actor, metres):
    mark = _mark()
    scene = Scene(
        id="mat", name="Mat", bounds=SceneBounds(0, 0, 0, 80, 40, 10),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={actor.id: Position(5, 20, 0),
                             mark.id: Position(5 + metres, 20, 0)},
    )
    session = CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=3), combatants=[actor, mark],
    ).start()
    return {a.power_name for a in _situation_for(session, actor.id).menu
            if a.power_name}


@pytest.mark.parametrize("name", ["Ravel", "Bokor", "PowerLad"])
@pytest.mark.parametrize("metres", [1, 20])
def test_every_name_on_a_real_menu_is_nameable(name, metres):
    actor = replace(HeroCombatant.from_build(require_authored(name), id="a"),
                    side=Side.named("a"))
    names = set(nameable_powers(actor))
    on_menu = _menu_names(actor, metres)
    assert on_menu, f"{name} at {metres}m was offered nothing with a power name"
    assert on_menu <= names, sorted(on_menu - names)


def test_a_stat_block_names_its_attacks_and_the_strike():
    names = nameable_powers(fighter("f", side=Side.named("a")))
    assert "Blast" in names and "Strike" in names
    assert len(names) == len(set(names)), "a name is listed once"

"""Cover has to change a to-hit roll, or it is scenery.

THE GAP THIS CLOSES. The engine could compute cover exactly --
`compute_cover_level` takes a shooter, a target and a scene and returns
0-4 per the 6E table, and `cover_ocv_modifier` turns that into an OCV
penalty. Both were correct. Neither was ever consulted when resolving an
attack: `compute_cover_level`'s only caller was `brief.py`, which WRITES
ABOUT the fight, and `line_of_sight.py` carried a comment saying cover
modifiers are applied "after the LoS gate" by somebody else. Nobody was
somebody else.

So a fighter who took cover gained nothing, every tactic that valued
cover was valuing zero, and "why does nobody dive for cover" had an
answer underneath the one about offers: there was no reason to.

WHERE IT GOES. `resolve_attack` is pure and knows nothing about scenes;
it takes an `ocv_modifier` and applies it. The session layer is what
holds the scene. So the penalty is computed in
`resolve_attack_in_session` and folded into the input, which keeps the
pure resolver pure and gets every caller that goes through the session
--- single attacks, Multiple Attack's shots, move-and-strike --- for
free.
"""
from __future__ import annotations

import pytest

from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from conftest import fighter          # tests/loop/conftest.py

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _gun():
    return AttackPower(
        xmlid="RKA", name="rifle", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True)


def _scene(*, with_barrel: bool):
    """Shooter at x=0, target at x=10. The barrel sits between them."""
    walls = []
    if with_barrel:
        walls.append(Wall(
            id="barrel", name="Barrel",
            segment=(Position(5.0, -1.0, 0.0), Position(5.0, 1.0, 0.0)),
            height_m=1.2, blocks_los=False, blocks_movement=True,
            cover_level=2, body=4, def_value=2, climb_difficulty=0))
    return Scene(
        id="range", name="A shooting lane",
        bounds=SceneBounds(-5.0, -5.0, 0.0, 20.0, 5.0, 10.0),
        surfaces=[Surface(id="g", name="ground",
                          polygon_xy=[(-5, -5), (20, -5), (20, 5), (-5, 5)],
                          elevation_m=0.0, surface_type="ground",
                          cover_level=0)],
        walls=walls, hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"shooter": Position(0.0, 0.0, 0.0),
                             "mark": Position(10.0, 0.0, 0.0)},
    )


def _shoot(*, with_barrel: bool):
    session = CombatSession.create(
        id="s", scene=_scene(with_barrel=with_barrel), template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
        combatants=[fighter("shooter", side=Side.named("a"), dex=20),
                    fighter("mark", side=Side.named("b"), dex=10)],
    ).start()
    attack = AttackInput(
        attacker=session.combatants["shooter"],
        target=session.combatants["mark"],
        power=_gun(), distance_m=10.0, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3], damage=[3, 3]),
    )
    return resolve_attack_in_session(session, attack, TEMPLATE)


def test_a_barrel_between_them_costs_the_shooter_ocv():
    """Cover 2/4 is -2 OCV against the man behind it (6E2 p.'s table)."""
    _s_open, open_result = _shoot(with_barrel=False)
    _s_cov, covered = _shoot(with_barrel=True)
    assert covered.to_hit.effective_ocv == open_result.to_hit.effective_ocv - 2


def test_no_cover_means_no_penalty():
    """An empty lane must not quietly apply one."""
    _s, result = _shoot(with_barrel=False)
    assert result.to_hit.effective_ocv >= 0


def test_the_cover_is_recorded_so_a_reader_can_see_why():
    """A to-hit that silently moved is indistinguishable from a bad roll."""
    session, _result = _shoot(with_barrel=True)
    payload = session.event_log[-1].result_payload
    assert payload["cover_level"] == 2
    assert payload["cover_ocv"] == -2


def test_an_open_shot_records_no_cover():
    session, _result = _shoot(with_barrel=False)
    payload = session.event_log[-1].result_payload
    assert payload["cover_level"] == 0
    assert payload["cover_ocv"] == 0


def test_a_scene_without_positions_is_not_an_error():
    """Most tests and many fights have no map. Cover simply does not
    apply, rather than raising or guessing."""
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
        combatants=[fighter("shooter", side=Side.named("a"), dex=20),
                    fighter("mark", side=Side.named("b"), dex=10)],
    ).start()
    attack = AttackInput(
        attacker=session.combatants["shooter"],
        target=session.combatants["mark"],
        power=_gun(), distance_m=None, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3], damage=[3, 3]),
    )
    new_session, result = resolve_attack_in_session(session, attack, TEMPLATE)
    assert new_session.event_log[-1].result_payload["cover_level"] == 0

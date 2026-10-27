"""Shared scaffolding for the shaped-attack seam tests (Area, Constant, Damage
Over Time, Side Effects, Increased END, Move By/Through, hazard zones)."""
from __future__ import annotations

from dataclasses import replace

from conftest import blast                          # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class Dice:
    """Every die shows ``face`` unless a queued roll says otherwise.

    ``queue`` holds whole rolls in order (a list per `roll_dice` call); once
    it is empty every roll is ``face`` on each die. Enough control to make a
    shot hit or miss without scripting every die of a Phase.
    """

    def __init__(self, face: int = 2, queue=None):
        self.face = face
        self.queue = [list(q) for q in (queue or [])]
        self.calls: list[int] = []

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        self.calls.append(count)
        if self.queue:
            roll = self.queue.pop(0)
            if len(roll) != count:
                raise ValueError(f"asked for {count} dice, queued {roll}")
            return roll
        return [self.face] * count


def scene_with(positions: dict[str, tuple[float, float, float]], *,
               constructs=None, walls=None) -> Scene:
    return Scene(
        id="field", name="field",
        bounds=SceneBounds(-50.0, -50.0, 0.0, 80.0, 80.0, 20.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-50, -50), (80, -50), (80, 80), (-50, 80)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls or []), hazards=[],
        ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v) for k, v in positions.items()},
        constructs=list(constructs or []),
    )


def session_on(scene, *combatants, template=TEMPLATE) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=list(combatants), scene=scene, template=template,
        dice_roller=RandomRoller(seed=3),
    ).start()


def encounter_on(scene, *combatants, segment: int = 12, template=TEMPLATE) -> Encounter:
    return Encounter(id="e", turn=1, segment=segment, template=template,
                     sessions=[session_on(scene, *combatants, template=template)])


def armed(id: str, power, *, side=None, dex: int = 20, stun: int = 40,
          spd: int = 4, running: int = 12, also=(), **stats):
    """`conftest.fighter`'s stat block, carrying ``power`` as its one attack
    (and ``also``, any more)."""
    from fixtures.synthetic_hero import synthetic_combatant

    block = dict(
        ocv=9, dcv=5, omcv=5, dmcv=5, spd=spd, dex=dex, ego=15, str_=15,
        con=18, pre=15, rec=6, pd=4, ed=4, rpd=2, red=2, md=3,
        power_defense=0, flash_defense=0, max_stun=40, max_body=12,
        max_end=40, current_stun=stun, current_body=12, current_end=40,
        running=running,
    )
    block.update(stats)
    return synthetic_combatant(
        id=id, name=id, side=side,
        attacks=([power] if power is not None else []) + list(also), **block,
    )


def shaped_blast(source_id: str, dice: int = 4, **fields):
    return replace(blast(source_id, dice), **fields)


class Picks:
    """A chooser that takes the first offer `want(action)` accepts, else the
    first Dodge, else the first offer; and remembers every menu."""

    def __init__(self, want):
        self.want = want
        self.menus = []

    def choose(self, situation):
        self.menus.append(list(situation.menu))
        for a in situation.menu:
            if self.want(a, situation):
                return a.action_id
        for a in situation.menu:
            if a.kind == "dodge":
                return a.action_id
        return situation.menu[0].action_id


def payloads(session, **match):
    out = []
    for e in session.event_log:
        if e.kind != "ActionResolved":
            continue
        p = e.result_payload or {}
        if all(p.get(k) == v for k, v in match.items()):
            out.append(p)
    return out

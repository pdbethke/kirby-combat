"""A building remembers being shot.

`Construct` is frozen and its docstring states the contract: "a
Construct's `body` is the CURRENT body for one resolution; damage flows
out as events and back via DRIVER HYDRATION on the next step." The driver
was kirby-api. When the turn loop became the driver it never hydrated
anything, and `constructs_in` re-projects every wall from `scene.walls`
on each call --- so every shot hit a brand new building.

Measured at the O.K. Corral the first afternoon walls were attackable:
the Harwood House has BODY 8 and took 0, 2, 6 and 0 across four shots ---
eight BODY against eight --- and reported `destroyed=False` every time.
Nothing in this engine could ever be knocked down.

Folded from the log, absolute rather than a delta, like every other fold
here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.scene.construct import constructs_in
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_dice import RandomRoller
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_engine,
)


def _scene():
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 12.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (12, -2), (12, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[Wall(id="harwood", name="Harwood House",
                    segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
                    height_m=6.0, blocks_los=True, blocks_movement=True,
                    cover_level=4, body=8, def_value=4)],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={},
    )


class _Log:
    def __init__(self, events=()):
        self.event_log = list(events)
        self.scene = _scene()


def _base() -> dict:
    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _hit(obj_id: str, body: int) -> list:
    d = ActionDeclared(**_base(), combatant_id="wyatt",
                       action_type="attack_construct", targets=[obj_id])
    r = ActionResolved(**_base(), declaration_event_id=d.id,
                       result_payload={"kind": "attack_construct",
                                       "target_id": obj_id,
                                       "body_dealt": body})
    return [d, r]


def _harwood(session):
    return next(c for c in constructs_in(session.scene, session=session)
                if c.obj_id == "harwood")


def test_an_untouched_building_is_at_full_body():
    assert _harwood(_Log()).body == 8


def test_a_shot_building_carries_the_damage():
    assert _harwood(_Log(_hit("harwood", 3))).body == 5


def test_shots_accumulate():
    """The defect exactly: three shots adding to its whole BODY. Each one
    used to land on a brand new building.

    A building at zero is not a building at zero --- it is gone, see
    `test_a_building_already_down_is_no_longer_there`. This asserts the
    accumulation right up to the edge of that."""
    log = _Log(_hit("harwood", 3) + _hit("harwood", 3))
    assert _harwood(log).body == 2


def test_damage_beyond_its_body_does_not_wrap_around():
    """Overkill leaves rubble, not a building with negative BODY."""
    log = _Log(_hit("harwood", 6) + _hit("harwood", 6))
    assert not [c for c in constructs_in(log.scene, session=log)
                if c.obj_id == "harwood"]


def test_damage_to_one_building_is_not_damage_to_another():
    log = _Log(_hit("flys", 5))
    assert _harwood(log).body == 8


def test_without_a_session_it_is_the_authored_building():
    """Every caller that has no fight in hand --- and there are several ---
    keeps getting the scene as authored."""
    assert next(c for c in constructs_in(_scene()) if c.obj_id == "harwood").body == 8


def test_a_building_already_down_is_no_longer_there():
    """It came down on Tom McLaury, Frank McLaury and Billy Clanton --- and
    then came down on them three more times, because a destroyed
    construct stayed in the scene and could be knocked over again.

    Rubble is not a building. Once its BODY is gone it stops being a
    thing you can shoot, hide behind, or drop on somebody.
    """
    log = _Log(_hit("harwood", 8))
    assert not [c for c in constructs_in(log.scene, session=log)
                if c.obj_id == "harwood"]


def test_a_building_still_standing_is_still_there():
    log = _Log(_hit("harwood", 7))
    assert [c for c in constructs_in(log.scene, session=log)
            if c.obj_id == "harwood"]


# ---- and it stops being in the way ----

def test_a_collapsed_building_stops_blocking():
    """It came down on three men and they were still hiding behind it.

    `constructs_in` drops rubble, but `cover.py`, `perception.py` and
    `movement_legality.py` all read `scene.walls` directly and nothing
    hydrates that --- so a flattened house still granted cover, still
    blocked line of sight, and still turned a man's movement back.

    Taking it off the board is part of bringing it down, so
    `bring_it_down` does both.
    """
    from kirby_combat.collapse import bring_it_down
    from kirby_combat.scene.construct import construct_from_wall
    from kirby_combat.template import CombatTemplate

    log = _Log()
    session = _live_session()
    wall = session.scene.walls[0]
    after, _ = bring_it_down(session, construct_from_wall(wall),
                             roller=RandomRoller(seed=5),
                             template=CombatTemplate.default_6e_superheroic())
    assert [w.id for w in after.scene.walls] == []


def test_bringing_down_one_building_leaves_the_others():
    from kirby_combat.collapse import bring_it_down
    from kirby_combat.scene.construct import construct_from_wall
    from kirby_combat.template import CombatTemplate

    session = _live_session(second=True)
    target = construct_from_wall(session.scene.walls[0])
    after, _ = bring_it_down(session, target, roller=RandomRoller(seed=5),
                             template=CombatTemplate.default_6e_superheroic())
    assert [w.id for w in after.scene.walls] == ["flys"]


def _live_session(second: bool = False):
    from conftest import fighter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate

    scene = _scene()
    if second:
        from dataclasses import replace as _replace

        extra = Wall(id="flys", name="Fly's",
                     segment=(Position(5.5, 0.0, 0.0), Position(5.5, 10.0, 0.0)),
                     height_m=6.0, blocks_los=True, blocks_movement=True,
                     cover_level=4, body=8, def_value=4)
        scene = _replace(scene, walls=list(scene.walls) + [extra])
    return CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("ike", side=Side.named("cow"))],
    ).start()

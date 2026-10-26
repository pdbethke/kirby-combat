"""Rapid Fire at a wall was offered and could not be fired.

The construct block of `enumerate_actions` offers `rapid_fire:<wall>:...:3`
(6E2 p.75, Multiple Attack at one target), and `_resolve_rapid_fire` looked
the target up in `session.combatants` --- where no wall lives --- and raised
`UnresolvableAction`. A 20-fight random-chooser sweep skipped 34--46 of them.

The seam: every rapid_fire offer at a construct must resolve, through the
same object-damage rule a single shot at that construct uses (6E2 p.172:
subtract the object's defense from each attack's BODY, per attack), and the
damage must stay on the wall for the next shot.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.constructs import constructs_in, damage_taken
from kirby_combat.encounter import Encounter
from kirby_combat.loop.run import run_phase
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _shed(body=30, def_value=2):
    return Wall(id="shed", name="Tool Shed",
                segment=(Position(6.0, 0.0, 0.0), Position(6.0, 10.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value)


def _encounter(seed: int) -> Encounter:
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[_shed()], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"lad": Position(2.0, 5.0, 0.0),
                             "ike": Position(10.0, 5.0, 0.0)},
    )
    session = CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=seed),
        combatants=[fighter("lad", side=Side.named("x"), dex=30),
                    fighter("ike", side=Side.named("y"), dex=10)],
    ).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


class _RapidFireTheShed:
    def __init__(self):
        self.offered: list[str] = []

    def choose(self, situation):
        rf = [a for a in situation.menu
              if a.kind == "rapid_fire" and a.targets_construct]
        self.offered.extend(a.action_id for a in rf)
        return (rf[0] if rf else situation.menu[0]).action_id


def test_rapid_fire_offered_at_a_wall_resolves_and_the_wall_keeps_the_damage():
    for seed in range(8):
        chooser = _RapidFireTheShed()
        result = run_phase(_encounter(seed), chooser,
                           roller=RandomRoller(seed=seed),
                           on_unresolvable="raise")
        assert chooser.offered, "the shed should be offered as a Rapid Fire target"
        session = result.encounter.sessions[0]
        resolved = [e for e in session.event_log
                    if getattr(e, "kind", "") == "ActionResolved"
                    and (e.result_payload or {}).get("kind") == "rapid_fire"]
        assert len(resolved) == 1
        payload = resolved[0].result_payload
        assert payload["target_id"] == "shed"
        assert payload["targets_construct"] is True
        # One BODY roll per shot, the wall's defense off EACH (6E2 p.172).
        assert len(payload["shots"]) == 3
        assert all(s["body_through"] == max(0, s["body_rolled"] - 2)
                   for s in payload["shots"])
        assert payload["body_dealt"] == sum(s["body_through"] for s in payload["shots"])
        # The fold sees it: the next shot lands on a damaged wall.
        assert damage_taken(session, "shed") == payload["body_dealt"]
        shed = next(c for c in constructs_in(session.scene, session=session)
                    if c.obj_id == "shed")
        assert shed.body == 30 - payload["body_dealt"]

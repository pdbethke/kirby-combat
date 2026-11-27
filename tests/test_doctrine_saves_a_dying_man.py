"""Doctrine lets men bleed to death, and it does not have to.

`stabilize` has been offered 94 times across the western benchmarks and
taken zero times. Measured on the corral, six fights: **31 offers, 29
bleeding ticks, and not one attempt to help.**

The rule is not ambiguous about the stakes (6E2 p.109): a character at 0
or negative BODY is DYING, loses 1 BODY per Turn, and death is inevitable
without intervention. 6E2 p.115 gives the attempt to anybody --- "even
just the Everyman 8- roll" --- and Doc Holliday at this fight carries
PARAMEDICS 11.

So every piece was built and wired: the bleeding rules, the Dying status,
the Paramedics roll, the `stabilize` offer keyed to the ALLY's condition.
The only thing missing was a tactic that ever picks it, which made the
whole feature inert in play --- a rung above "computed, delivered
nowhere": delivered, offered, and never chosen.

PRIORITY. Above `take_cover_when_hurt` (55) and `withdraw_when_outmatched`
(54): a man who will die this Turn without help outranks the actor's own
comfort. Below `exploit_susceptibility` (60), which is about ending the
fight outright.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Situation


class _Stats:
    ocv = dcv = 8
    omcv = dmcv = 5
    max_stun = max_body = max_end = 20
    str_ = con = 15
    dex = ego = int_ = 10
    pre = 15
    spd = 4
    pd = ed = 10
    rpd = red = 2


class _Man:
    """An ally or actor as the tactic layer sees one."""

    def __init__(self, id: str, *, body: int = 20, stun: int = 20):
        self.id = id
        self.name = id.title()
        self.current_body = body
        self.current_stun = stun
        self.current_end = 20
        self.max_stun = self.max_body = self.max_end = 20
        self.attacks = []

    def combat_stats(self):
        return _Stats()


def _situation(allies, *, skills=None, enemies=(), session=None) -> Situation:
    """Nobody left to shoot at him unless ``enemies`` says otherwise: the
    tactic kneels only where it is safe to (see the tests at the end)."""
    return Situation(
        actor=_Man("doc_holliday"), allies=allies,
        enemies=list(enemies),
        actor_skills=dict(skills or {"PARAMEDICS": 11}),
        session=session,
    )


def _tactic():
    from kirby_combat.tactics.catalog.stabilize_the_dying import StabilizeTheDying

    return StabilizeTheDying()


def test_a_dying_ally_makes_the_tactic_apply():
    """0 BODY is DYING, not knocked out (6E2 p.105)."""
    assert _tactic().applicable(_situation([_Man("morgan_earp", body=0)]))


def test_a_bleeding_ally_below_zero_still_applies():
    assert _tactic().applicable(_situation([_Man("morgan_earp", body=-4)]))


def test_healthy_allies_do_not_trigger_it():
    assert not _tactic().applicable(_situation([_Man("wyatt_earp", body=20)]))


def test_a_knocked_out_but_not_dying_ally_does_not_trigger_it():
    """STUN 0 with BODY intact is unconscious, not bleeding out. Spending
    the Phase on Paramedics there wastes it."""
    assert not _tactic().applicable(
        _situation([_Man("wyatt_earp", body=12, stun=0)]))


def test_a_man_with_no_allies_left_has_nobody_to_save():
    assert not _tactic().applicable(_situation([]))


def test_the_plan_names_the_dying_man():
    """A stabilize roll's difficulty depends on WHICH man is bleeding
    (-1 per -2 BODY), so a plan that names no target is unexecutable."""
    plan = _tactic().execute(_situation([
        _Man("wyatt_earp", body=20), _Man("morgan_earp", body=-2),
    ]))
    assert plan.steps
    assert plan.steps[0].kind == "stabilize"
    assert plan.steps[0].target_id == "morgan_earp"


def test_the_worst_off_man_is_chosen_first():
    """Bleeding costs 1 BODY a Turn and death arrives at -BODY, so the
    man nearest it is the one who cannot wait."""
    plan = _tactic().execute(_situation([
        _Man("wyatt_earp", body=-1), _Man("morgan_earp", body=-9),
    ]))
    assert plan.steps[0].target_id == "morgan_earp"


def test_it_is_registered_in_the_catalogue():
    """A tactic nothing can reach is documentation."""
    from kirby_combat.tactics.library import all_tactics

    assert "stabilize_the_dying" in {t.name for t in all_tactics()}


def test_a_dead_ally_is_past_saving():
    """6E2 p.109: at negative his starting BODY he is dead."""
    assert not _tactic().applicable(_situation([_Man("wyatt_earp", body=-20)]))



# ---- Only where it is safe to kneel (Peter, 2026-11-27) --------------------
#
# JUDGEMENT, not a rule: 6E2 p.109 says a dying man can be stabilized, not
# when. Peter chose: stop fighting to do it only when no enemy is standing,
# or when you are in cover from every one of them, or when he dies at the
# end of this Turn without help. At the corral, three Earps bandaged Wyatt
# in the open while the McLaurys shot them down, and he had seven Turns.

def _scene(*walls, **positions):
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-4.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-4, -2), (14, -2), (14, 14), (-4, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _wall():
    from kirby_combat.scene.scene import Position, Wall
    return Wall(id="trough", name="Trough",
                segment=(Position(5.0, 0.0, 0.0), Position(5.0, 10.0, 0.0)),
                height_m=2.0, blocks_los=True, blocks_movement=True)


def _on_the_lot(scene):
    from types import SimpleNamespace
    return SimpleNamespace(scene=scene)


def test_not_while_a_man_with_a_gun_stands_in_the_open_with_him():
    wounded = [_Man("wyatt_earp", body=-3)]
    open_lot = _on_the_lot(_scene(doc_holliday=(2.0, 5.0), tom_mclaury=(8.0, 5.0)))
    assert not _tactic().applicable(_situation(
        wounded, enemies=[_Man("tom_mclaury")], session=open_lot))


def test_with_no_map_nobody_can_say_he_is_covered():
    assert not _tactic().applicable(_situation(
        [_Man("wyatt_earp", body=-3)], enemies=[_Man("tom_mclaury")]))


def test_behind_cover_from_every_enemy_he_can_kneel():
    behind = _on_the_lot(_scene(_wall(), doc_holliday=(2.0, 5.0), tom_mclaury=(8.0, 5.0)))
    assert _tactic().applicable(_situation(
        [_Man("wyatt_earp", body=-3)], enemies=[_Man("tom_mclaury")], session=behind))


def test_not_when_one_enemy_still_has_a_clear_shot():
    """Cover is per shooter (6E2 p.45): covered from one is not covered."""
    flanked = _on_the_lot(_scene(_wall(), doc_holliday=(2.0, 5.0), tom_mclaury=(8.0, 5.0),
                                 frank_mclaury=(2.0, 12.0)))
    assert not _tactic().applicable(_situation(
        [_Man("wyatt_earp", body=-3)],
        enemies=[_Man("tom_mclaury"), _Man("frank_mclaury")], session=flanked))


def test_under_fire_when_he_dies_at_the_end_of_this_turn():
    """1 BODY a Turn and dead at negative his starting BODY (6E2 p.109):
    at -19 of 20 the next bleed kills him, so it is now or never."""
    open_lot = _on_the_lot(_scene(doc_holliday=(2.0, 5.0), tom_mclaury=(8.0, 5.0)))
    situation = _situation([_Man("wyatt_earp", body=-19), _Man("morgan_earp", body=-2)],
                           enemies=[_Man("tom_mclaury")], session=open_lot)
    assert _tactic().applicable(situation)
    assert _tactic().execute(situation).steps[0].target_id == "wyatt_earp"

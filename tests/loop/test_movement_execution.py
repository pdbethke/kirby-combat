"""Movement actually moves people.

WHAT WAS WRONG. The engine could decide a move completely and then forget
it. `movement_reach` is a full pure resolver -- mode, start, destination,
capacity in; landing position out, clamped by walls and surfaces, with any
fall. `MovementAction.resolve` charged the END and emitted the event.

And nothing wrote the position down. Measured 2026-09-06:

* `MovementResolved` carries `from_pos` and `to_pos`, and
  `MovementAction.resolve` built one with BOTH HARDCODED TO None.
* `scene.combatant_positions` is read all over the engine -- the range
  gate, line of sight, cover, Images placement -- and written NOWHERE
  outside a test fixture.

So a fight on a map was frozen: everyone enumerated, attacked and was
attacked from where they started, forever. Nothing raised, because a
stationary fight is a perfectly valid fight. Exactly the shape of every
other defect this carve-out has turned up -- green suites, silent wrong.
"""
from __future__ import annotations

import pytest

from conftest import blast, fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.scene.placement import commit_move, move_toward, position_of
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _scene(**positions: Position) -> Scene:
    return Scene(
        id="street", name="A Street",
        bounds=SceneBounds(-100, -100, 0, 200, 200, 50),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions=dict(positions),
    )


def _session(scene: Scene | None = None, *, apart: float = 30.0):
    scene = scene or _scene(
        actor=Position(0.0, 0.0, 0.0), mark=Position(apart, 0.0, 0.0),
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=6),
        combatants=[
            fighter("actor", side=Side.named("heroes"), dex=25),
            fighter("mark", side=Side.named("villains"), dex=15),
        ],
    ).start()


def _act(kind: str, **kw) -> LegalAction:
    return LegalAction(
        action_id=kw.pop("action_id", f"{kind}:mark"), kind=kind,
        target_id=kw.pop("target_id", "mark"),
        power_xmlid=None, power_name=None, summary=kind, **kw,
    )


def _resolve(session, action):
    return resolve_chosen(
        session, session.combatants["actor"], action,
        template=TEMPLATE, roller=RandomRoller(seed=6),
    )


# ---- position_of: absent is not the origin ----

def test_a_combatant_not_on_the_map_has_no_position():
    """Not on the map is not the same as at (0,0,0) -- one is absent from
    every distance calculation, the other is adjacent to whoever stands
    there."""
    assert position_of(_scene(), "actor") is None
    assert position_of(None, "actor") is None


# ---- The move is actually written down ----

def test_moving_toward_an_enemy_changes_the_position():
    session = _session(apart=30.0)
    before = position_of(session.scene, "actor")
    assert before.x == 0.0

    _resolve(session, _act("move"))

    after = position_of(session.scene, "actor")
    assert after.x > before.x, "the mover never moved"


def test_a_full_move_is_capped_by_the_characters_running():
    """12m of RUNNING does not cross 30m of street in one Phase."""
    session = _session(apart=30.0)
    _resolve(session, _act("move"))
    assert position_of(session.scene, "actor").x == pytest.approx(12.0)


def test_a_reachable_destination_is_reached_exactly():
    session = _session(apart=5.0)
    _resolve(session, _act("move"))
    assert position_of(session.scene, "actor").x == pytest.approx(5.0)


def test_the_outcome_says_whether_the_destination_was_reached():
    session = _session(apart=30.0)
    resolved = _resolve(session, _act("move"))
    payload = resolved.session.event_log[-1].result_payload
    assert payload["reached"] is False, "30m is beyond a 12m Move"
    assert payload["landing"][0] == pytest.approx(12.0)


def test_a_partial_move_is_a_real_move():
    """Falling short is not failing: the mover is somewhere new."""
    session = _session(apart=100.0)
    _resolve(session, _act("move"))
    assert position_of(session.scene, "actor").x > 0


# ---- Refusals rather than guesses ----

def test_moving_toward_someone_who_is_not_on_the_map_refuses():
    session = _session(_scene(actor=Position(0.0, 0.0, 0.0)))
    with pytest.raises(UnresolvableAction, match="move"):
        _resolve(session, _act("move"))


def test_a_mover_who_is_not_on_the_map_refuses():
    session = _session(_scene(mark=Position(10.0, 0.0, 0.0)))
    with pytest.raises(UnresolvableAction, match="move"):
        _resolve(session, _act("move"))


def test_repositioning_without_a_destination_refuses():
    """The offer chose the point. Re-deciding it here would mean the menu
    advertised one place and the engine went to another."""
    session = _session()
    with pytest.raises(UnresolvableAction, match="reposition"):
        _resolve(session, _act("reposition", target_id=None))


# ---- Reposition, and the strike that follows one ----

def test_repositioning_goes_where_the_offer_said():
    session = _session()
    _resolve(session, _act(
        "reposition", target_id=None, reposition_dest=(0.0, 8.0, 0.0),
    ))
    landed = position_of(session.scene, "actor")
    assert (landed.x, landed.y) == pytest.approx((0.0, 8.0))


def test_a_reposition_strike_attacks_from_the_NEW_position():
    """The move buys the shot -- that is why these are one action and not
    two.

    Five metres, because the Phase also holds an attack. This asked for
    nine and asserted it landed there, which on a Running 12 character is
    a FULL Move (6E2 p.26: "more than half of a character's movement
    distance ... can't perform any other Action in that Phase"). What the
    test is actually about -- the shot comes from where he ended up, not
    where he began -- is unchanged by moving a legal distance.
    """
    session = _session(apart=10.0)
    before = session.combatants["mark"].state.current_stun

    resolved = _resolve(session, _act(
        "reposition_strike", reposition_dest=(5.0, 0.0, 0.0),
        _attack_view=blast("eb", dice=8),
    ))

    assert position_of(session.scene, "actor").x == pytest.approx(5.0)
    assert resolved.result is not None
    assert resolved.session.combatants["mark"].state.current_stun <= before


def test_a_reposition_strike_is_capped_at_a_half_move():
    """Ask for nine and get six. 6E2 p.26 measures a Full Move by the
    DISTANCE covered, so the cap is what keeps the following attack legal
    rather than a check that refuses it after the fact."""
    session = _session(apart=20.0)
    running = float(session.combatants["actor"].hero.characteristic_value("RUNNING"))

    _resolve(session, _act(
        "reposition_strike", reposition_dest=(9.0, 0.0, 0.0),
        _attack_view=blast("eb", dice=8),
    ))

    assert position_of(session.scene, "actor").x == pytest.approx(running / 2.0)


def test_move_strike_closes_on_the_target_then_strikes():
    session = _session(apart=10.0)
    resolved = _resolve(session, _act(
        "move_strike", _attack_view=blast("eb", dice=8),
    ))
    assert position_of(session.scene, "actor").x > 0.0
    assert resolved.result is not None


# ---- commit_move keeps decision and recording apart ----

def test_commit_move_records_a_decision_it_did_not_make():
    """`movement_reach` never moves anybody and `commit_move` never judges
    legality. Keeping them apart is what stops a 'could I get there?' query
    mutating the world."""
    session = _session()
    _, outcome = move_toward(
        session, "actor", Position(4.0, 0.0, 0.0),
        mode="running", distance_m=12.0,
    )
    assert position_of(session.scene, "actor").x == pytest.approx(4.0)

    commit_move(session, "mark", outcome)
    assert position_of(session.scene, "mark").x == pytest.approx(4.0)


def test_committing_with_no_scene_is_a_no_op_not_a_crash():
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=6),
        combatants=[fighter("actor", side=Side.named("heroes"))],
    ).start()
    out, outcome = move_toward(
        session, "actor", Position(1.0, 0.0, 0.0), mode="running", distance_m=12.0,
    )
    assert outcome is None
    assert out is session


# ---- The event finally says where the mover was ----

def test_the_movement_event_carries_the_starting_position():
    """`from_pos` was hardcoded to None since the event was written, so a
    replayer could see THAT a move happened and never where from."""
    from kirby_combat.actions.movement.running import Running

    session = _session()
    _new, event = Running.make(distance_m=6.0, move_type="half", base_inches=12).resolve(
        session, "actor",
    )
    assert event.from_pos == {"x": 0.0, "y": 0.0, "z": 0.0}

"""Sessions the state-view tests look at.

Built from flat stat blocks so nothing here needs a Hero Designer
template -- CI has no corpus. The same construction as
`tests/serialization/test_roundtrip.py::_ct`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, run_phase
from kirby_combat.models import StatBlockCombatant
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import FlashApplied, make_author_engine
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_SUPERHEROIC
from kirby_dice import RandomRoller


def a_roller(seed: int = 7) -> RandomRoller:
    """`state_view` takes its roller from the caller and has no default.

    A test that wants the same answer twice passes the same seed; the api
    derives one from the sequence it is replaying.
    """
    return RandomRoller(seed=seed)


def a_fighter(id_: str) -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=id_.title(), ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def two_fighter_session() -> CombatSession:
    """No scene: nobody is on a map, so every position reads None."""
    return CombatSession.create(
        id="s1",
        combatants=[a_fighter("alice"), a_fighter("bob")],
        scene=None,
        template=RAW_SUPERHEROIC,
        dice_roller=None,
    )


def _floor() -> Scene:
    """Twenty metres square of ground, and the two of them standing on it.

    `scene/placement.py` holds the READERS (`position_of`) and the move
    door (`commit_move`); it has no placer, so the standing positions a
    fight opens with are the ones the Scene is built carrying. That is
    the same construction every scene test in this suite uses.
    """
    return Scene(
        id="floor", name="Floor",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(
                id="ground", name="Ground",
                polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                elevation_m=0.0, surface_type="ground",
                cover_level=0, is_supporting=True,
            ),
        ],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={
            "alice": Position(x=0.0, y=0.0, z=0.0, facing=0.0),
            "bob": Position(x=4.0, y=0.0, z=0.0, facing=3.14),
        },
    )


def placed_session() -> CombatSession:
    """The same two, standing somewhere."""
    return CombatSession.create(
        id="s2",
        combatants=[a_fighter("alice"), a_fighter("bob")],
        scene=_floor(),
        template=RAW_SUPERHEROIC,
        dice_roller=None,
    )


def a_fight_that_has_happened() -> CombatSession:
    """A started session with an acting order and a Phase behind it.

    NOT the flat stat blocks the other fixtures use: `enumerate_actions`
    refuses one, so `run_phase` cannot step a fight made of them. These
    are `kirby_combat.synthetic`'s build-backed fighters, which still
    need no Hero Designer corpus.
    """
    encounter = Encounter(
        id="e", turn=1, segment=12,
        sessions=[
            CombatSession.create(
                id="s3",
                combatants=[
                    synthetic_combatant(
                        id="alice", name="Alice", spd=4, dex=25,
                        side=Side.named("x"),
                    ),
                    synthetic_combatant(
                        id="bob", name="Bob", spd=4, dex=10,
                        side=Side.named("y"),
                    ),
                ],
                scene=None,
                template=RAW_SUPERHEROIC,
                dice_roller=RandomRoller(seed=7),
            ).start()
        ],
    )
    return run_phase(
        encounter, FirstLegalChooser(), roller=RandomRoller(seed=7),
    ).session


def flashed_session() -> CombatSession:
    """Alice Flashed in the Sight Group, so she perceives nobody.

    A Flash rides the LOG and needs no geometry, which is what makes it
    the clean lever for a perception test: `cannot_perceive` reads the
    Flash off the session and answers without a scene.
    """
    session = CombatSession.create(
        id="s4",
        combatants=[a_fighter("alice"), a_fighter("bob")],
        scene=None,
        template=RAW_SUPERHEROIC,
        dice_roller=None,
    ).start()
    return apply_event(session, FlashApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        target_id="alice", sense_group="sight", segments=3,
    ))


class _InvisibilityPower:
    """An INVISIBILITY power with no group adder, which `perception.
    invisibility_groups` reads as the Sight Group — the HERO default."""

    xmlid = "INVISIBILITY"
    alias = "Invisibility"
    adders: list = []
    sub_powers: list = []


def an_invisible_fighter_session(close_enough_for_the_fringe: bool = False):
    """Alice bought Invisibility; bob is an enemy and carol an ally.

    Ten metres apart by default, which is well beyond the 2 m Fringe, so
    no PER roll is drawn and the answer is a read. With
    ``close_enough_for_the_fringe`` bob stands 1 m away, inside the
    Fringe, so HIS pair is decided by a PER roll -- the one place this
    view is not a projection. Carol stays at ten metres in both cases, so
    every test has a deterministic pair to compare against the rolled
    one.
    """
    bob_x = 1.0 if close_enough_for_the_fringe else 10.0
    alice = synthetic_combatant(id="alice", name="Alice", side=Side.named("x"))
    alice.hero.powers.append(_InvisibilityPower())
    scene = Scene(
        id="floor", name="Floor",
        bounds=SceneBounds(0, 0, 0, 40, 40, 40),
        surfaces=[
            Surface(
                id="ground", name="Ground",
                polygon_xy=[(0, 0), (40, 0), (40, 40), (0, 40)],
                elevation_m=0.0, surface_type="ground",
                cover_level=0, is_supporting=True,
            ),
        ],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={
            "alice": Position(x=0.0, y=0.0, z=0.0, facing=0.0),
            "bob": Position(x=bob_x, y=0.0, z=0.0, facing=3.14),
            "carol": Position(x=0.0, y=10.0, z=0.0, facing=3.14),
        },
    )
    return CombatSession.create(
        id="s5",
        combatants=[
            alice,
            synthetic_combatant(id="bob", name="Bob", side=Side.named("y")),
            synthetic_combatant(id="carol", name="Carol", side=Side.named("x")),
        ],
        scene=scene,
        template=RAW_SUPERHEROIC,
        dice_roller=None,
    ).start()

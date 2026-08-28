"""Conditions-must-bite: tests proving a condition actually changes an
outcome, not merely that ``statuses_for`` can name it.

This file is APPENDED TO by later tasks in the same plan (Task 3: Stunned
denies actions -- Abort/movement/Presence Attacks; Task 4 lives in its own
file). Keep new sections clearly divided by a comment banner naming the
task, the way this file's own Task 2 section is divided below, so
additions read naturally alongside what is already here.

------------------------------------------------------------------------
Task 2: Stunned degrades CV (``kirby_combat/cv_modifiers.py``)
------------------------------------------------------------------------

> 6E2 p.106, "Stunning": "A Stunned character's DCV and DMCV instantly
> drop to 1/2 (as do the modifiers for making Placed Shots against him)."
> 6E2 p.39 (condition modifier table): Stunned -> DCV 1/2, hit locations
> 1/2; Recovering from being Stunned -> DCV 1/2, hit locations 1/2 (the
> SAME penalty -- it does not lift the instant the ``stunned`` status id
> clears; see ``cv_modifiers.py::_stunned_or_recovering``).

Reuses the exact attacker/target/session fixtures and the qualifying-hit
recipe from ``tests/test_statuses.py`` (10d6 EB vs no defenses, well
within CON) so a hit here is known-good against the same helper the
Stunned status-id tests already cover.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.cv_modifiers import (
    CVModifiers, apply_cv_factor, apply_hit_location_factor,
    cv_modifiers_for, effective_dcv_for, effective_dmcv_for,
    effective_ocv_for,
)
from kirby_combat.dice import FakeRoller
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import SegmentAdvanced, make_author_engine
from kirby_combat.template import CombatTemplate


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=list(combatants),
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _advance(session: CombatSession, to_segment: int, to_turn: int) -> CombatSession:
    """Mirrors ``test_statuses.py::_advance`` -- appends the same
    ``SegmentAdvanced`` event ``Encounter.advance_segment`` would, without
    needing a live ``Encounter``."""
    evt = SegmentAdvanced(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        from_segment=session.timeline.segment,
        to_segment=to_segment,
        to_turn=to_turn,
    )
    return apply_event(session, evt)


def _attacker_for_stun(con: int = 15) -> "HeroCombatant":
    return synthetic_combatant(
        id="attacker", name="Attacker",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[
            AttackPower(
                xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
    )


def _target_for_stun(
    spd: int = 4, dcv: int = 9, dmcv: int = 7, con: int = 15,
    current_stun: int = 30, current_body: int = 15,
) -> "HeroCombatant":
    return synthetic_combatant(
        id="bob", name="bob",
        ocv=8, dcv=dcv, omcv=5, dmcv=dmcv,
        spd=spd, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=current_stun, current_body=current_body, current_end=30,
    )


def _hitting_attack_for_stun(attacker, target) -> AttackInput:
    """10d6 normal EB, no defenses on target -> 36 STUN, blows through any
    reasonable CON (identical recipe to ``test_statuses.py``)."""
    return AttackInput(
        attacker=attacker,
        target=target,
        power=attacker.attacks[0],
        distance_m=0,
        aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
        ),
    )


def _stun(session: CombatSession, attacker, target) -> CombatSession:
    attack = _hitting_attack_for_stun(attacker, target)
    session, result = resolve_attack_in_session(session, attack, session.template)
    assert "Stunned" in result.status_changes  # sanity: the hit really qualifies
    return session


# --------------------------------------------------------------------- #
# Baseline / non-interference: an unstunned combatant is unaffected
# --------------------------------------------------------------------- #

def test_unstunned_combatant_cv_is_unchanged():
    attacker, target = _attacker_for_stun(), _target_for_stun(dcv=9, dmcv=7)
    session = _session(attacker, target)

    mods = cv_modifiers_for(session, "bob")
    assert mods == CVModifiers()  # every factor 1.0

    assert effective_dcv_for(session, "bob") == 9
    assert effective_dmcv_for(session, "bob") == 7
    assert effective_ocv_for(session, "bob") == 8


def test_apply_cv_factor_matches_6e2_p39_negative_worked_examples():
    """6E2 p.39's own two worked examples, pinned directly: 'if a
    character has OCV -4, halving reduces it to -6 (-4 plus half of -4,
    or -2). If he has OCV -3, halving reduces it to -4.' Halving a
    negative CV makes it WORSE, not better."""
    assert apply_cv_factor(-4, 0.5) == -6
    assert apply_cv_factor(-3, 0.5) == -4


def test_apply_cv_factor_positive_cv_still_shrinks_toward_zero():
    """Sanity: only the NEGATIVE branch flips direction; positive CVs
    behave as before (round up in the character's favour)."""
    assert apply_cv_factor(8, 0.5) == 4
    assert apply_cv_factor(5, 0.5) == 3   # ceil(2.5)


def test_apply_cv_factor_rejects_an_ungrounded_factor():
    """6E2 p.39 only grounds 1.0 (no-op), 0.5 (halving), and 0.0
    (override to zero) -- anything else has no page to ground its
    negative-CV arithmetic in, so this function refuses rather than
    inventing one (this task's explicit brief)."""
    import pytest
    with pytest.raises(ValueError):
        apply_cv_factor(9, 0.25)


def test_apply_hit_location_factor_matches_apply_cv_factor_on_positives():
    """The two functions agree when the base value is positive/zero --
    they only diverge on a negative input, which is where p.39's
    stacking clause (apply_cv_factor) and p.106's plain halving
    (apply_hit_location_factor) actually differ."""
    assert apply_hit_location_factor(8, 0.5) == apply_cv_factor(8, 0.5) == 4


def test_apply_cv_factor_and_apply_hit_location_factor_disagree_on_a_penalty():
    """The bug this task fixed, pinned so it cannot silently come back:
    apply_cv_factor is for a combatant's OWN CV (p.39's 'further penalty
    on an already-negative CV' stacking rule -- makes -8 WORSE, -12).
    apply_hit_location_factor is for the Placed-Shot table constant
    (p.106's plain 'the modifiers... drop to half' -- makes -8 a SMALLER
    penalty, -4). Same input, opposite direction, because they ground
    two different rules."""
    assert apply_cv_factor(-8, 0.5) == -12
    assert apply_hit_location_factor(-8, 0.5) == -4


def test_apply_cv_factor_is_a_noop_at_factor_one():
    assert apply_cv_factor(9, 1.0) == 9
    assert apply_cv_factor(-8, 1.0) == -8


# --------------------------------------------------------------------- #
# Stunned halves DCV and DMCV (6E2 p.106)
# --------------------------------------------------------------------- #

def test_stunned_combatant_dcv_is_halved():
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4, dcv=9, dmcv=7)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    mods = cv_modifiers_for(session, "bob")
    assert mods.dcv_factor == 0.5

    # 9 * 0.5 = 4.5 -> rounds up (this task's stated rounding choice; see
    # cv_modifiers.py::apply_cv_factor's docstring) -> 5.
    assert effective_dcv_for(session, "bob") == 5


def test_stunned_combatant_dmcv_is_halved():
    """6E2 p.106 names DMCV explicitly ('DCV and DMCV instantly drop to
    1/2'), so a mental attacker sees the same halving a physical one does."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4, dcv=9, dmcv=7)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    mods = cv_modifiers_for(session, "bob")
    assert mods.dmcv_factor == 0.5

    # 7 * 0.5 = 3.5 -> rounds up -> 4.
    assert effective_dmcv_for(session, "bob") == 4


def test_stunned_does_not_touch_ocv():
    """6E2 p.106/p.39 halve DCV/DMCV/hit-location -- OCV is untouched."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    mods = cv_modifiers_for(session, "bob")
    assert mods.ocv_factor == 1.0
    assert effective_ocv_for(session, "bob") == target.ocv


def test_stunned_halves_the_placed_shot_hit_location_modifier():
    """6E2 p.106: 'as do the modifiers for making Placed Shots against
    him' -- the OCV penalty an ATTACKER suffers for a Placed Shot against
    a Stunned target is itself halved (easier to aim precisely)."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    mods = cv_modifiers_for(session, "bob")
    assert mods.hit_location_factor == 0.5

    # Head shot ocvMod is -8 (tables.py::HIT_LOCATIONS); halved -> -4.
    # Uses apply_hit_location_factor, NOT apply_cv_factor -- 6E2 p.106
    # halves the modifier's magnitude unconditionally (a smaller
    # penalty), unlike p.39's sign-aware "further penalty on an
    # already-negative CV" rule apply_cv_factor implements. See
    # test_apply_cv_factor_and_apply_hit_location_factor_disagree_on_a_penalty
    # below for the two functions' diverging answer on the same input.
    assert apply_hit_location_factor(-8, mods.hit_location_factor) == -4


# --------------------------------------------------------------------- #
# The penalty survives into the recovery Phase (6E2 p.39) even though the
# `stunned` status id itself clears at the START of that Phase
# (statuses.py::_is_stunned's documented early-clear behaviour).
# --------------------------------------------------------------------- #

def test_stunned_cv_penalty_still_applies_during_recovery_phase():
    """SPD 4 -> Phases at segments 3, 6, 9, 12 (tables.py
    SPEED_TO_SEGMENTS). Session starts on Segment 12 (6E2 p.20, combat
    begins Segment 12), so the hit lands on bob's own Phase. Advancing to
    Segment 3 is bob's NEXT full Phase -- his recovery Phase (6E2 p.107).
    The `stunned` status id clears there (see test_statuses.py's own
    coverage of that edge), but the CV penalty must not: p.39 gives
    Recovering-from-being-Stunned the SAME DCV 1/2 penalty."""
    from kirby_combat.statuses import STUNNED, statuses_for

    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4, dcv=9, dmcv=7)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)
    session = _advance(session, to_segment=3, to_turn=2)  # bob's recovery Phase

    # Sanity: the narrower status id really has cleared by now (proves this
    # test is exercising the gap, not accidentally re-testing `stunned`).
    assert STUNNED not in statuses_for(session, "bob")

    mods = cv_modifiers_for(session, "bob")
    assert mods.dcv_factor == 0.5
    assert mods.dmcv_factor == 0.5
    assert effective_dcv_for(session, "bob") == 5   # 9 * 0.5 -> ceil -> 5


def test_stunned_cv_penalty_clears_after_the_recovery_phase_ends():
    """One more of bob's Phase segments past the recovery Phase (Segment
    6) is his NEXT Phase after that -- fully recovered, per 6E2 p.107
    ('he cannot act until his next Phase'). Both the penalty and the
    status id should be gone."""
    attacker, target = _attacker_for_stun(), _target_for_stun(spd=4, dcv=9, dmcv=7)
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    session = _advance(session, to_segment=1, to_turn=2)
    session = _advance(session, to_segment=2, to_turn=2)
    session = _advance(session, to_segment=3, to_turn=2)  # recovery Phase starts
    session = _advance(session, to_segment=4, to_turn=2)
    session = _advance(session, to_segment=5, to_turn=2)
    session = _advance(session, to_segment=6, to_turn=2)  # his NEXT Phase: fully clear

    mods = cv_modifiers_for(session, "bob")
    assert mods.dcv_factor == 1.0
    assert mods.dmcv_factor == 1.0
    assert effective_dcv_for(session, "bob") == 9
    assert effective_dmcv_for(session, "bob") == 7


# ----------------------------------------------------------------------- #
# Task 3: Stunned denies actions -- above all, the Abort
# (``kirby_combat/actions/reactive/abort.py``,
# ``kirby_combat/scene/movement_legality.py``,
# ``kirby_combat/pre_attacks/presence.py``)
# ----------------------------------------------------------------------- #
#
# > 6E2 p.106, "Stunning": "The character remains Stunned and can take no
# > Action until his next Phase (he cannot even Abort to a defensive
# > Action). A character who's Stunned or recovering from being Stunned
# > can take no Actions, take no Recoveries (except his free Post-Segment
# > 12 Recovery), cannot move, and cannot be affected by Presence Attacks.
# > Stunned characters typically retain their grip on objects they are
# > holding."
#
# Denial style used at each of the three enforced call sites, and why:
#
#   - ``mark_aborting`` (Abort/Dodge/Block/Dive-for-Cover's single choke
#     point) RAISES ``ValueError`` -- matching its own existing sibling
#     precondition failure ("already aborted this phase") two lines away
#     in the same function; every caller already handles this function
#     raising.
#   - ``movement_reach`` RETURNS an unreachable ``MovementOutcome``
#     (``reachable=False``, ``landing=from_pos``, ``fall=None``) --
#     matching every OTHER "can't get there" case this pure resolver
#     already reports the same way (a blocked wall, an out-of-water swim,
#     ...); this function never raises for a legality failure anywhere
#     else, so a Stunned refusal keeping that shape is the consistent
#     choice.
#   - ``resolve_presence_attack`` RETURNS a ``PresenceAttackResult`` whose
#     ``effect`` is forced to ``"no_effect"`` -- matching how this pure
#     resolver already reports "the attack didn't land" (a roll that
#     falls short of the target's PRE also gets ``"no_effect"``, per
#     ``presence_attack_effect``'s own docstring); the caller reads the
#     same field either way.
#
# All three inconsistent in RAISE-vs-RETURN terms across the whole set,
# but each one internally consistent with its own function's existing
# failure-reporting convention -- which is the point: matching what a
# call site ALREADY does with failure, not inventing one uniform style
# that would be new to two of the three.


def test_stunned_combatant_cannot_abort_to_dodge():
    """The exploitable gap this task closes: before Task 3, nothing in
    ``kirby_combat/actions/`` checked any condition (measured via
    ``grep -rn "stunned" kirby_combat/actions/`` returning nothing), so a
    Stunned combatant could still Abort to Dodge."""
    import pytest
    from kirby_combat.actions.reactive.dodge import Dodge

    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    with pytest.raises(ValueError):
        Dodge.declare(session, "bob")


def test_stunned_combatant_cannot_abort_to_block():
    """6E2 p.106's parenthetical names Block explicitly by naming ANY
    'defensive Action' -- test the second reactive destination too, not
    just Dodge, so a narrower fix (e.g. gating only ``Dodge.declare``)
    cannot pass."""
    import pytest
    from kirby_combat.actions.reactive.block import Block

    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    with pytest.raises(ValueError):
        Block.declare(session, "bob")


def test_unstunned_combatant_can_still_abort_to_dodge_and_block():
    """Control: the denial must not regress an ordinary Abort."""
    from kirby_combat.actions.reactive.block import Block
    from kirby_combat.actions.reactive.dodge import Dodge

    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)

    session, evt = Dodge.declare(session, "bob")
    assert evt.to_action == "dodge"

    # A fresh session (nobody has aborted yet) so Block's declare isn't
    # blocked by the "already aborted this phase" precondition instead.
    session2 = _session(_attacker_for_stun(), _target_for_stun())
    session2, evt2 = Block.declare(session2, "bob")
    assert evt2.to_action == "block"


def test_stunned_combatant_cannot_move():
    """6E2 p.106: 'cannot move'. ``movement_reach`` stays a pure resolver
    of Scene + Positions when ``session`` isn't passed (see its own
    docstring) -- this test is the one exercising the new, OPTIONAL
    session-aware path."""
    from kirby_combat.scene.movement_legality import movement_reach
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )

    scene = Scene(
        id="arena", name="Open Field",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
        ],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={},
    )
    from_pos = Position(2, 10, 0)
    to_pos = Position(10, 10, 0)

    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)
    session = _stun(session, attacker, target)

    out = movement_reach(
        "running", from_pos, to_pos, distance_m=12, scene=scene,
        combatant_id="bob", session=session,
    )
    assert out.reachable is False
    assert out.landing == from_pos
    assert out.fall is None


def test_unstunned_combatant_can_move():
    """Control: passing `session` for an unstunned combatant must
    round-trip today's un-Stunned movement behaviour unchanged."""
    from kirby_combat.scene.movement_legality import movement_reach
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )

    scene = Scene(
        id="arena", name="Open Field",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
        ],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={},
    )
    from_pos = Position(2, 10, 0)
    to_pos = Position(10, 10, 0)

    attacker, target = _attacker_for_stun(), _target_for_stun()
    session = _session(attacker, target)  # nobody hit -- bob is unstunned

    out = movement_reach(
        "running", from_pos, to_pos, distance_m=12, scene=scene,
        combatant_id="bob", session=session,
    )
    assert out.reachable is True
    assert out.landing == to_pos


def test_movement_reach_without_a_session_is_unaffected():
    """Signature-discipline control: the pre-Task-3 call shape (no
    `session=` at all) must behave EXACTLY as before -- no Stunned check
    can run without a session to check it against."""
    from kirby_combat.scene.movement_legality import movement_reach
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )

    scene = Scene(
        id="arena", name="Open Field",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
        ],
        walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={},
    )
    from_pos = Position(2, 10, 0)
    to_pos = Position(10, 10, 0)

    out = movement_reach("running", from_pos, to_pos, distance_m=12, scene=scene)
    assert out.reachable is True
    assert out.landing == to_pos


def _pre_attacker(pre: int = 25):
    return synthetic_combatant(
        id="prea", name="prea", ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=15, str_=20, con=15, pre=pre, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _pre_target(pre: int = 10):
    return synthetic_combatant(
        id="pret", name="pret", ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=15, str_=15, con=15, pre=pre, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_stunned_target_is_unaffected_by_a_presence_attack():
    """6E2 p.106: 'cannot be affected by Presence Attacks'. A roll that
    would ordinarily blow well past every tier on the table (PRE 25 ->
    5 dice, all 6s -> roll_total=30, target PRE=10 -> margin=20 ->
    'awed') is forced to 'no_effect' when `target_stunned=True`."""
    from kirby_combat.pre_attacks.presence import resolve_presence_attack

    attacker, target = _pre_attacker(pre=25), _pre_target(pre=10)
    result = resolve_presence_attack(
        attacker, target, dice_values=[6, 6, 6, 6, 6], target_stunned=True,
    )
    assert result.effect == "no_effect"


def test_unstunned_target_is_affected_by_the_same_presence_attack():
    """Control, same inputs minus the flag: proves the roll really would
    have landed, so the Stunned test above is exercising a real denial,
    not a roll that simply missed."""
    from kirby_combat.pre_attacks.presence import resolve_presence_attack

    attacker, target = _pre_attacker(pre=25), _pre_target(pre=10)
    result = resolve_presence_attack(
        attacker, target, dice_values=[6, 6, 6, 6, 6],
    )
    assert result.effect != "no_effect"
    assert result.effect == "awed"


def test_presence_attack_default_target_stunned_false_is_unaffected():
    """Signature-discipline control: omitting `target_stunned` entirely
    (every pre-Task-3 caller) must match the un-flagged call above."""
    from kirby_combat.pre_attacks.presence import resolve_presence_attack

    attacker, target = _pre_attacker(pre=25), _pre_target(pre=10)
    result = resolve_presence_attack(
        attacker, target, dice_values=[6, 6, 6, 6, 6],
    )
    assert result.effect == "awed"


# --------------------------------------------------------------------- #
# The two rows that need NO code -- pinned so a later change can't
# silently break either one.
# --------------------------------------------------------------------- #

def test_stunned_combatant_still_receives_the_free_post_12_recovery():
    """6E2 p.106: 'take no Recoveries (except his free Post-Segment 12
    Recovery)'. 6E2 p.131: 'After Segment 12 each Turn, all characters
    (even Stunned ones) get a free Post-Segment 12 Recovery.' MEASURED:
    this engine has no voluntary Recovery action at all
    (`encounter.py::_apply_post_12_recovery` applies to every combatant
    unconditionally, no consciousness/status filter) -- so there is
    nothing to deny; this test pins that the free Recovery keeps
    reaching a Stunned combatant."""
    from kirby_combat.encounter import Encounter
    from kirby_combat.statuses import STUNNED, statuses_for

    attacker = _attacker_for_stun()
    # `resolve_attack_in_session` records the Stunned status via the
    # ActionResolved payload (see `_stun`'s docstring-adjacent sanity
    # assert) but does NOT mutate `state.current_stun` itself -- so bob's
    # starting current_stun is set directly here, below its max, purely
    # so the free Recovery below has visible room to raise it.
    target = synthetic_combatant(
        id="bob", name="bob", ocv=8, dcv=9, omcv=5, dmcv=7,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=60, max_body=15, max_end=30,
        current_stun=14, current_body=15, current_end=30,
    )
    session = _session(attacker, target)
    session = _stun(session, attacker, target)  # records "Stunned" (sanity-asserted by `_stun`)

    assert STUNNED in statuses_for(session, "bob")
    stun_before = session.combatants["bob"].state.current_stun
    assert stun_before == 14

    enc = Encounter(id="e1", segment=12, sessions=[session])
    out = enc.advance_segment()

    bob_after = out.sessions[0].combatants["bob"]
    assert bob_after.state.current_stun > stun_before


def test_stunned_combatant_retains_grip_on_held_objects():
    """6E2 p.106: 'Stunned characters typically retain their grip on
    objects they are holding.' MEASURED: already the default behaviour --
    this engine has no equipment/inventory model that anything could
    strip on a status change (no field on `HeroCombatant`/`HeroCombatState`
    represents a 'held object' distinct from a combatant's own powers).
    Pinned here as a no-op: the combatant's held/equipped gear -- its
    `attacks` (weapons/powers) and `defenses` (worn/carried protection) --
    are byte-for-byte identical before and after taking a Stunning hit,
    so a later change that started dropping gear on Stun would break this
    test rather than shipping silently. Bob is given a real shield
    (`defenses`) and a real weapon (`attacks`) here, rather than relying
    on the shared `_target_for_stun` fixture's empty defaults, so an
    equality check against two empty lists can't pass by accident."""
    from kirby_combat.models import DefenseItem

    attacker = _attacker_for_stun()
    target = synthetic_combatant(
        id="bob", name="bob", ocv=8, dcv=9, omcv=5, dmcv=7,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[
            AttackPower(
                xmlid="HANDTOHANDATTACK", name="Sword", damage_dice=6,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="pd", range_m=0,
                uses_str=True, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
        defenses=[DefenseItem(name="Shield", pd=3, ed=3, is_resistant=False)],
    )
    session = _session(attacker, target)

    before_attacks = list(session.combatants["bob"].attacks)
    before_defenses = list(session.combatants["bob"].defenses)
    assert before_attacks and before_defenses  # sanity: not vacuously empty

    session = _stun(session, attacker, target)

    after_attacks = list(session.combatants["bob"].attacks)
    after_defenses = list(session.combatants["bob"].defenses)

    assert after_attacks == before_attacks
    assert after_defenses == before_defenses

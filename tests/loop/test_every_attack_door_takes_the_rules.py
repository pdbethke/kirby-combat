"""Every door into `resolve_attack_in_session` gets the same rules.

THE DEFECT THIS GUARDS. 6E2 p.127's blind penalty, p.55's Dodge, p.52's
Surprised and 6E1 p.139's Drained CV were applied by the plain-attack
resolver and by NONE of the other six callers that reach
`resolve_attack_in_session`: `_reposition(then_attack=True)` (move-strike),
`_resolve_shots` (rapid fire / multiple attack / sweep), `_resolve_throw`,
`_resolve_push`, `_maneuver_attack` and `_maybe_stray` each assembled their
own `AttackInput` and got none of it. A man in a Darkness field was blind
to a punch and sighted to a move-and-strike.

That is this engine's dominant defect shape -- a rule at one door and not
the others -- and it has been found at four doors over three rounds. The
fix is not six more copies of the wiring. It is one fold on the path all
seven already take, and this file is the test that says so in a way a
seventh door cannot quietly escape: it captures every `AttackInput` that
actually reaches the pure resolver and asserts the rules are on it.
"""
from __future__ import annotations

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
import pytest
from conftest import blast, fighter                 # tests/loop/conftest.py
from kirby_dice import RandomRoller

from kirby_combat.actions import recording
from kirby_combat.cv_modifiers import apply_cv_factor
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: Both men well inside one Sight-Group Darkness field, three metres apart
#: --- close enough that a move-strike can close the gap on a Half Move.
HERE = Position(20.0, 20.0, 1.5)
THERE = Position(23.0, 20.0, 1.5)


def _darkness() -> Construct:
    """A Sight-Group Darkness field covering the whole fight (6E1 p.188)."""
    return Construct(
        obj_id="dz1", kind="darkness_zone",
        polygon_xy=[(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)],
        elevation_range_m=(0.0, 5.0),
        sense_group="sight", creator_immune=False,
        source_combatant_id=None,
    )


def _fight():
    scene = Scene(
        id="dark", name="Dark", bounds=SceneBounds(0, 0, 0, 40, 40, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        constructs=[_darkness()],
        combatant_positions={"brute": HERE, "mark": THERE},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=3),
        combatants=[
            fighter("brute", side=Side.named("villains"), dice=2),
            fighter("mark", side=Side.named("heroes"), dice=2),
        ],
    ).start()


@pytest.fixture
def captured(monkeypatch):
    """Every `(AttackInput, AttackResult)` that reaches the pure resolver.

    Patched at `recording.resolve_attack` --- the last thing
    `resolve_attack_in_session` calls --- so a resolver that skipped the
    fold shows up here with a bare input, whatever route it took to get in.

    The RESULT is captured as well as the input, and the assertions below
    read the result. A CV penalty can arrive on either of two channels: the
    `ocv_modifier` / `dcv_modifier` deltas, or a `Surprise` that
    `resolution/to_hit.py` applies itself. Asserting on the modifier alone
    would have called a correctly halved DCV a failure the moment the
    halving came in as p.52 rather than p.9 -- which is exactly what the
    halve-once JUDGEMENT arranges. `ToHitResult` is where the two meet.
    """
    seen: list = []
    original = recording.resolve_attack

    def spy(attack, template):
        result = original(attack, template)
        seen.append((attack, result))
        return result

    monkeypatch.setattr(recording, "resolve_attack", spy)
    return seen


def _action(kind: str, **kw) -> LegalAction:
    power = blast("brute-eb", dice=2)
    fields = dict(
        action_id=f"{kind}:mark", kind=kind, target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary=kind,
        _attack_view=power,
    )
    fields.update(kw)
    return LegalAction(**fields)


#: One entry per door this test can drive end to end. `_maybe_stray` needs
#: a third body standing in the melee and `_resolve_throw` needs a held
#: object, so neither is driven here --- both reach the same
#: `resolve_attack_in_session`, and the assertion below is on what that
#: function does rather than on who called it.
DOORS = [
    ("attack", lambda: _action("attack")),
    ("move_strike", lambda: _action("move_strike")),
    ("trip", lambda: _action("trip")),
    ("multiple_attack", lambda: _action(
        "multiple_attack", action_id="multiple_attack:self:all",
        target_id=None, _attack_view=None)),
    ("push", lambda: _action("push", action_id="push:mark:brute-eb")),
]


@pytest.mark.parametrize("kind,make", DOORS, ids=[d[0] for d in DOORS])
def test_every_door_folds_the_blind_penalty(kind, make, captured):
    """6E2 p.127 reaches the roll through whichever resolver was chosen.

    Both men are in the dark, so neither can perceive the other: the
    attacker's OCV is reduced and the target's DCV is halved. The exact
    OCV row differs by door (a maneuver is hand-to-hand, a blast is at
    Range, and p.9 gives them different rows), so this asserts that the
    penalty is THERE rather than pinning a number -- the numbers are pinned
    per row in `test_blind_attacks.py` and `test_blind_maneuvers.py`.
    """
    session = _fight()
    base_ocv = int(session.combatants["brute"].ocv)
    base_dcv = int(session.combatants["mark"].dcv)
    resolve_chosen(
        session, session.combatants["brute"], make(),
        template=TEMPLATE, roller=RandomRoller(seed=11),
    )
    assert captured, f"{kind} never reached resolve_attack_in_session"
    for _attack, result in captured:
        assert result.to_hit.effective_ocv < base_ocv, (
            f"{kind}: the attacker is blind and paid nothing for it"
        )
        assert result.to_hit.effective_dcv < base_dcv, (
            f"{kind}: the target is blind and defends at full DCV"
        )


@pytest.mark.parametrize("kind,make", DOORS, ids=[d[0] for d in DOORS])
def test_every_door_halves_the_blind_targets_dcv_exactly_once(kind, make, captured):
    """The JUDGEMENT in `_fold_session_cvs`: p.52's Surprised and p.9's
    inability to sense share a cause here, and the defender is halved once.
    DCV 5 -> 3, never 5 -> 3 -> 2."""
    session = _fight()
    base = int(session.combatants["mark"].dcv)
    resolve_chosen(
        session, session.combatants["brute"], make(),
        template=TEMPLATE, roller=RandomRoller(seed=11),
    )
    assert captured, f"{kind} never reached resolve_attack_in_session"
    for _attack, result in captured:
        assert result.to_hit.effective_dcv == apply_cv_factor(base, 0.5), (
            f"{kind}: DCV halved more than once"
        )

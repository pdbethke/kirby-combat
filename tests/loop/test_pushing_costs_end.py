"""A Push that costs nothing is not a Push.

`reposition_push` is the offer to shove past your normal movement --- the
menu prints it as "+8m for +10 END" --- and `LegalAction.push_end` carries
that cost. Enumeration sets it (`enumeration.py`, beside
`push_move_metres`); `_resolve_reposition` reads `reposition_dest` and
NOTHING ELSE, so the actor got the extra metres for free in every fight
this engine has run.

6E2 p.135 is the rule this engine already cites for Pushing --- END is
what a Push is bought with, which is why `actions/push.py` names
`PUSH_END_PER_POINT = 1` and enumeration prices the movement Push at
`PUSH_END = 10`. The number was computed, printed on the offer, and never
charged.

Found by sweeping every dataclass field for reads: `push_end` was set and
read by nobody.

WHERE IT IS SPENT, and why not at apply time. `session/apply.py`
deliberately treats `ActionResolved` as log-only --- "combatant stat
mutations in apply would force log replay to mirror combatant state, which
is more brittle" --- so this folds the END beside the resolution, exactly
as `_apply_damage` folds damage and `MovementAction.resolve` already
applies its own END spend.

THE DISTANCE WAS NEVER THE BUG. Enumeration computes the destination
inside the pushed radius and puts it on `reposition_dest`, so the actor
does travel the extra metres. Only the price was missing.
"""
from __future__ import annotations

from conftest import fighter                       # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
import kirby_combat.loop.resolvers  # noqa: F401  -- registers the kinds
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _push_offer(end=10, dest=(3.0, 0.0, 0.0)):
    return LegalAction(
        action_id="reposition_push:running:0", kind="reposition_push",
        target_id=None, power_xmlid=None, power_name=None,
        summary="Push running to shove past", mode="running",
        reposition_dest=dest, push_move_m=8.0, push_end=end,
    )


def _plain_offer(dest=(3.0, 0.0, 0.0)):
    return LegalAction(
        action_id="reposition:running:0", kind="reposition",
        target_id=None, power_xmlid=None, power_name=None,
        summary="Reposition", mode="running", reposition_dest=dest,
    )


def _session():
    """A real map: `_reposition` moves somebody, and there is nowhere to
    move on a scene-less session."""
    from kirby_combat.scene.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )
    from kirby_combat.session.combat_session import CombatSession

    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 20.0, 20.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (20, -2), (20, 20), (-2, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"tom": Position(0.0, 0.0, 0.0),
                             "virgil": Position(10.0, 0.0, 0.0)},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()


def _resolve(offer):
    session = _session()
    before = session.combatants["tom"].state.current_end
    out = resolve_chosen(session, session.combatants["tom"], offer,
                         template=TEMPLATE, roller=RandomRoller(seed=3))
    after = out.session.combatants["tom"].state.current_end
    return before, after


def test_a_push_costs_the_end_the_offer_advertised():
    before, after = _resolve(_push_offer(end=10))
    assert before - after == 10


def test_an_ordinary_reposition_costs_nothing_extra():
    """The guard: only a PUSH is charged, and only for the push."""
    before, after = _resolve(_plain_offer())
    assert before == after


def test_the_cost_is_the_offers_number_not_a_constant():
    """`push_end` is on the action because enumeration prices it; a
    resolver that hardcoded 10 would drift the moment the price moved."""
    before, after = _resolve(_push_offer(end=4))
    assert before - after == 4


def test_end_cannot_go_below_zero():
    """A fighter with less END than the Push costs is not left owing.

    HERO's rule for spending END you do not have (take STUN instead) is
    NOT implemented here and is not claimed to be; this only refuses to
    record a negative pool.
    """
    session = _session()
    drained = session.combatants["tom"]
    object.__setattr__(drained.state, "current_end", 3)
    out = resolve_chosen(session, drained, _push_offer(end=10),
                         template=TEMPLATE, roller=RandomRoller(seed=3))
    assert out.session.combatants["tom"].state.current_end == 0

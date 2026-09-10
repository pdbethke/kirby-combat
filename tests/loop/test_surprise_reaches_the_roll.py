"""The last mile: a real attack, on a real target who cannot see it coming.

Everything this needs already existed and none of it was joined up.
`_resolve_hide` recorded who lost track of whom; `perception.is_surprised`
could say whether a target perceives its attacker, and its own docstring
noted that the rest "is applied by the driver, which knows the combat
clock"; `resolution/surprise.py` now reads 6E2 p.52 off that answer. This
is the test that the DRIVER asks.

Before it, `is_surprised` had zero production callers in the engine.
"""
from __future__ import annotations

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _alley():
    return Scene(
        id="alley", name="alley",
        bounds=SceneBounds(-30, -30, 0.0, 30, 30, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-30, -30), (30, -30), (30, 30), (-30, 30)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"sneak": Position(0.0, 0.0, 0.0),
                             "mark": Position(3.0, 0.0, 0.0)},
    )


def _session():
    return CombatSession.create(
        id="s", scene=_alley(), template=TEMPLATE,
        dice_roller=RandomRoller(seed=7),
        combatants=[fighter("sneak", side=Side.named("a"), dex=30),
                    fighter("mark", side=Side.named("b"), dex=8)],
    ).start()


def _hide(session):
    """Spend the Phase hiding, and hand back the fight that remembers it."""
    return resolve_chosen(
        session, session.combatants["sneak"],
        LegalAction(action_id="hide", kind="hide", target_id=None,
                    power_xmlid=None, power_name=None, summary="hide"),
        template=TEMPLATE, roller=RandomRoller(seed=5),
    ).session


def _shoot(session):
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.run import distances_from

    actor = session.combatants["sneak"]
    target = session.combatants["mark"]
    menu = enumerate_actions(actor, [target], has_scene=True, scene=session.scene,
                             distances=distances_from(session.scene, actor, [target]))
    attack = next(m for m in menu if m.kind == "attack")
    return resolve_chosen(session, actor, attack, template=TEMPLATE,
                          roller=RandomRoller(seed=7))


def _hid_from_the_mark(session) -> bool:
    payload = session.event_log[-1].result_payload
    return "mark" in set(payload.get("unseen_by") or ())


def test_a_hidden_attacker_surprises_his_target():
    """The whole chain: Hide contests Stealth vs PER, the log remembers
    who lost him, `concealment` reads it back, `is_surprised` agrees, and
    6E2 p.52 halves the DCV that gets rolled against."""
    hidden = _hide(_session())
    if not _hid_from_the_mark(hidden):
        import pytest
        pytest.skip("this seed did not beat the mark's PER; the roll is not under test")
    audit = _shoot(hidden).result.audit_trail
    assert any("Surprised" in line for line in audit), audit


def test_an_attacker_who_never_hid_surprises_nobody():
    audit = _shoot(_session()).result.audit_trail
    assert not any("Surprised" in line for line in audit), audit


def test_hiding_halves_the_dcv_that_is_rolled_against():
    hidden = _hide(_session())
    if not _hid_from_the_mark(hidden):
        import pytest
        pytest.skip("this seed did not beat the mark's PER")
    from kirby_combat.cv_modifiers import apply_cv_factor

    sneaky = _shoot(hidden).result.to_hit
    open_ = _shoot(_session()).result.to_hit
    # 6E2 p.39's halving, not a bare division: a DCV of 5 goes to 3,
    # rounded in the defender's favour.
    assert sneaky.effective_dcv == apply_cv_factor(open_.effective_dcv, 0.5)
    assert sneaky.effective_dcv < open_.effective_dcv
